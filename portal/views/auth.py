import json
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_POST

from ..forms import (
    ChangePasswordForm,
    EmailForm,
    LoginForm,
    NewPasswordForm,
    ProfileForm,
)
from ..models import AccessToken, LoginAttempt, Passkey, User
from ..services import audit, emails, passkeys

LANGUAGE_CODES = {code for code, _name in settings.LANGUAGES}


def _safe_next(request, fallback="home"):
    target = request.POST.get("next") or request.GET.get("next") or ""
    if target and url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return target
    return fallback


def _with_language_cookie(response, language):
    response.set_cookie(
        settings.LANGUAGE_COOKIE_NAME,
        language,
        max_age=60 * 60 * 24 * 365,
        samesite="Lax",
        secure=settings.SESSION_COOKIE_SECURE,
    )
    return response


def _too_many_failures(email, ip):
    """Three caps over the same window; see LOGIN_MAX_FAILURES in settings."""
    since = timezone.now() - timedelta(minutes=settings.LOGIN_FAILURE_WINDOW_MINUTES)
    failures = LoginAttempt.objects.filter(success=False, created_at__gte=since)
    limit = settings.LOGIN_MAX_FAILURES
    return (
        failures.filter(email=email, ip=ip).count() >= limit
        or failures.filter(ip=ip).count() >= limit * 4
        or failures.filter(email=email).count() >= limit * 5
    )


def home(request):
    if not request.user.is_authenticated:
        return redirect("login")
    return redirect("manage_dashboard" if request.user.is_admin else "judge_dashboard")


@never_cache
@sensitive_post_parameters("password")
def login_view(request):
    if request.user.is_authenticated:
        return redirect("home")
    form = LoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"].strip().lower()
        ip = audit.client_ip(request)
        if _too_many_failures(email, ip):
            form.add_error(
                None,
                _("Too many failed attempts. Please wait %(minutes)s minutes and try again.")
                % {"minutes": settings.LOGIN_FAILURE_WINDOW_MINUTES},
            )
        else:
            user = authenticate(request, username=email, password=form.cleaned_data["password"])
            LoginAttempt.objects.create(email=email[:254], ip=ip, success=user is not None)
            if user is None:
                form.add_error(None, _("The email or password is not correct."))
            else:
                login(request, user)
                audit.log(request, "sign_in")
                return _with_language_cookie(redirect(_safe_next(request)), user.language)
    return render(
        request, "portal/auth/login.html", {"form": form, "next": _safe_next(request, "")}
    )


@require_POST
def logout_view(request):
    if request.user.is_authenticated:
        audit.log(request, "sign_out")
    logout(request)
    return redirect("login")


@never_cache
@sensitive_post_parameters("password1", "password2")
def accept_invite(request, token):
    """Invitation link: choose a password and sign in."""
    row = AccessToken.lookup(token, AccessToken.PURPOSE_INVITE)
    if row is None:
        return render(request, "portal/auth/link_invalid.html", {"kind": "invite"}, status=410)
    user = row.user
    form = NewPasswordForm(user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        row.used_at = timezone.now()
        row.save(update_fields=["used_at"])
        language = translation.get_language() or user.language
        if language in LANGUAGE_CODES and language != user.language:
            user.language = language
            user.save(update_fields=["language"])
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        audit.log(request, "invite_accepted")
        messages.success(request, _("Welcome. Your account is ready."))
        return _with_language_cookie(redirect("home"), user.language)
    return render(
        request,
        "portal/auth/set_password.html",
        {"form": form, "invited": user, "token": token, "purpose": AccessToken.PURPOSE_INVITE},
    )


@never_cache
def forgot_password(request):
    form = EmailForm(request.POST or None)
    sent = False
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"].strip().lower()
        user = User.objects.filter(email__iexact=email, is_active=True).first()
        recent = timezone.now() - timedelta(minutes=5)
        # Same response whether or not the address exists, and no more than
        # one link per account every five minutes.
        if (
            settings.EMAIL_CONFIGURED
            and user
            and user.has_signed_in
            and not user.access_tokens.filter(
                purpose=AccessToken.PURPOSE_RESET, created_at__gte=recent
            ).exists()
        ):
            emails.issue_password_reset(user, self_service=True)
            audit.log(request, "password_reset_requested", target=email, actor=user)
        sent = True
    return render(request, "portal/auth/forgot_password.html", {"form": form, "sent": sent})


@never_cache
@sensitive_post_parameters("password1", "password2")
def reset_password(request, token):
    row = AccessToken.lookup(token, AccessToken.PURPOSE_RESET)
    if row is None:
        return render(request, "portal/auth/link_invalid.html", {"kind": "reset"}, status=410)
    form = NewPasswordForm(row.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        row.used_at = timezone.now()
        row.save(update_fields=["used_at"])
        # A completed reset proves control of the mailbox: lift any sign-in
        # lock that failed guesses (the user's or an attacker's) left behind.
        LoginAttempt.objects.filter(email=row.user.email, success=False).delete()
        audit.log(request, "password_reset", actor=row.user)
        messages.success(request, _("Your password has been changed. Please sign in."))
        return redirect("login")
    return render(
        request,
        "portal/auth/set_password.html",
        {"form": form, "invited": None, "token": token, "purpose": AccessToken.PURPOSE_RESET},
    )


@login_required
@sensitive_post_parameters("current", "password1", "password2")
def account(request):
    user = request.user
    # Someone who signs in with a passkey has no password yet; they may add one.
    password_class = ChangePasswordForm if user.has_usable_password() else NewPasswordForm
    profile_form = ProfileForm(instance=user, prefix="profile")
    password_form = password_class(user, prefix="pw")
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "password":
            password_form = password_class(user, request.POST, prefix="pw")
            if password_form.is_valid():
                password_form.save()
                update_session_auth_hash(request, user)
                audit.log(request, "password_changed")
                messages.success(request, _("Your password has been changed."))
                return redirect("account")
        elif action == "remove_passkey":
            chosen = request.POST.get("passkey", "")
            key = get_object_or_404(Passkey, pk=int(chosen) if chosen.isdigit() else 0, user=user)
            if not user.has_usable_password() and user.passkeys.count() == 1:
                messages.error(
                    request,
                    _(
                        "This is your only way to sign in. Add another passkey or set a password "
                        "before removing it."
                    ),
                )
            else:
                key.delete()
                audit.log(request, "passkey_removed")
                messages.success(request, _("Passkey removed."))
            return redirect("account")
        else:
            profile_form = ProfileForm(request.POST, instance=user, prefix="profile")
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, _("Your details have been saved."))
                return redirect("account")
    return render(
        request,
        "portal/auth/account.html",
        {
            "profile_form": profile_form,
            "password_form": password_form,
            "passkeys": user.passkeys.all(),
            "has_password": user.has_usable_password(),
        },
    )


# --------------------------------------------------------------------------
# Passkeys. Each endpoint takes and returns JSON; see static/portal/js/passkeys.js.
# --------------------------------------------------------------------------

PASSKEY_ERRORS = {
    "expired": 400,
    "invalid": 400,
    "unknown": 400,
    "duplicate": 409,
}
LINK_PURPOSES = (AccessToken.PURPOSE_INVITE, AccessToken.PURPOSE_RESET)


def _json_body(request):
    if len(request.body) > 64 * 1024:
        return None
    try:
        data = json.loads(request.body or b"{}")
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _passkey_owner(request, data):
    """Who a new passkey is for: the signed-in user, or the holder of a
    one-time invitation or recovery link. Returns (user, token_row)."""
    token, purpose = data.get("token"), data.get("purpose")
    if token:
        row = (
            AccessToken.lookup(str(token), purpose)
            if isinstance(token, str) and purpose in LINK_PURPOSES
            else None
        )
        return (row.user, row) if row else (None, None)
    if request.user.is_authenticated:
        return request.user, None
    return None, None


@require_POST
@never_cache
def passkey_register_options(request):
    data = _json_body(request)
    user, _row = _passkey_owner(request, data) if data is not None else (None, None)
    if user is None:
        return JsonResponse({"error": "forbidden"}, status=403)
    return JsonResponse(passkeys.registration_options(request, user))


@require_POST
@never_cache
def passkey_register_verify(request):
    data = _json_body(request)
    user, row = _passkey_owner(request, data) if data is not None else (None, None)
    if user is None:
        return JsonResponse({"error": "forbidden"}, status=403)
    try:
        passkeys.register(request, user, data.get("credential"))
    except passkeys.PasskeyError as error:
        return JsonResponse({"error": str(error)}, status=PASSKEY_ERRORS[str(error)])
    audit.log(request, "passkey_added", actor=user)
    if row is None:
        messages.success(request, _("Passkey added."))
        return JsonResponse({"ok": True, "redirect": reverse("account")})

    # Came in on a one-time link: the link is now spent and the person is in.
    row.used_at = timezone.now()
    row.save(update_fields=["used_at"])
    if row.purpose == AccessToken.PURPOSE_INVITE:
        language = translation.get_language() or user.language
        if language in LANGUAGE_CODES and language != user.language:
            user.language = language
            user.save(update_fields=["language"])
    else:
        LoginAttempt.objects.filter(email=user.email, success=False).delete()
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    audit.log(
        request, "invite_accepted" if row.purpose == AccessToken.PURPOSE_INVITE else "sign_in"
    )
    messages.success(request, _("Welcome. Your account is ready."))
    return _with_language_cookie(
        JsonResponse({"ok": True, "redirect": reverse("home")}), user.language
    )


def _passkey_attempts_exhausted(ip):
    since = timezone.now() - timedelta(minutes=settings.LOGIN_FAILURE_WINDOW_MINUTES)
    failures = LoginAttempt.objects.filter(success=False, created_at__gte=since, ip=ip)
    return failures.count() >= settings.LOGIN_MAX_FAILURES * 4


@require_POST
@never_cache
def passkey_login_options(request):
    return JsonResponse(passkeys.authentication_options(request))


@require_POST
@never_cache
def passkey_login_verify(request):
    data = _json_body(request)
    ip = audit.client_ip(request)
    if data is None:
        return JsonResponse({"error": "invalid"}, status=400)
    if _passkey_attempts_exhausted(ip):
        return JsonResponse({"error": "throttled"}, status=429)
    try:
        user = passkeys.authenticate(request, data.get("credential"))
    except passkeys.PasskeyError as error:
        LoginAttempt.objects.create(email="(passkey)", ip=ip, success=False)
        return JsonResponse({"error": str(error)}, status=PASSKEY_ERRORS[str(error)])
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    audit.log(request, "sign_in", detail="passkey")
    target = data.get("next") if isinstance(data.get("next"), str) else ""
    if not (
        target
        and url_has_allowed_host_and_scheme(
            target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
        )
    ):
        target = reverse("home")
    return _with_language_cookie(JsonResponse({"ok": True, "redirect": target}), user.language)


@require_POST
def set_language(request):
    language = request.POST.get("language", "")
    target = _safe_next(request, request.META.get("HTTP_REFERER") or "home")
    if not url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        target = "home"
    response = redirect(target)
    if language in LANGUAGE_CODES:
        if request.user.is_authenticated and request.user.language != language:
            request.user.language = language
            request.user.save(update_fields=["language"])
        _with_language_cookie(response, language)
    return response


def forbidden(request, exception=None):
    return render(request, "portal/error.html", {"code": 403}, status=403)


def not_found(request, exception=None):
    return render(request, "portal/error.html", {"code": 404}, status=404)
