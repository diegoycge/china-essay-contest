"""Passkeys (WebAuthn): sign-in with a fingerprint, face or device PIN.

The browser and the person's device do the cryptography; this module issues
challenges and checks the signed answers. A passkey is bound to the site's
address, so it cannot be phished to a look-alike domain, and nothing stored
on the server is a secret.

Each ceremony is two requests: "options" (we issue a single-use challenge,
kept in the session) and "verify" (the device's answer comes back).
"""

import json
import time

from django.http.request import split_domain_port
from django.utils import timezone
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.exceptions import WebAuthnException
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from ..models import ContestSettings, Passkey

SESSION_KEY = "passkey_challenge"
CHALLENGE_LIFETIME_SECONDS = 300


class PasskeyError(Exception):
    """str() is a stable code: expired, invalid, unknown, duplicate."""


def _relying_party(request):
    """(rp_id, origin) for this request.

    Taken from the Host header, which Django has already checked against
    ALLOWED_HOSTS, so the same code works on localhost and in production.
    """
    host = request.get_host()
    domain, _port = split_domain_port(host)
    scheme = "https" if request.is_secure() else "http"
    return domain, f"{scheme}://{host}"


def _remember(request, kind, challenge, user_id=None):
    request.session[SESSION_KEY] = {
        "kind": kind,
        "challenge": bytes_to_base64url(challenge),
        "user": user_id,
        "at": time.time(),
    }


def _recall(request, kind, user_id=None):
    """Return the pending challenge, exactly once."""
    pending = request.session.pop(SESSION_KEY, None)
    if (
        not pending
        or pending.get("kind") != kind
        or pending.get("user") != user_id
        or time.time() - pending.get("at", 0) > CHALLENGE_LIFETIME_SECONDS
    ):
        raise PasskeyError("expired")
    return base64url_to_bytes(pending["challenge"])


def device_name(request):
    """A label for a new passkey, e.g. "Mac · Safari", from the browser's own description."""
    agent = request.META.get("HTTP_USER_AGENT", "")
    systems = (
        ("iPhone", "iPhone"),
        ("iPad", "iPad"),
        ("Android", "Android"),
        ("Mac OS X", "Mac"),
        ("Macintosh", "Mac"),
        ("Windows", "Windows"),
        ("CrOS", "Chromebook"),
        ("Linux", "Linux"),
    )
    browsers = (
        ("Edg/", "Edge"),
        ("Firefox/", "Firefox"),
        ("Chrome/", "Chrome"),
        ("Safari/", "Safari"),
    )
    system = next((label for token, label in systems if token in agent), "")
    browser = next((label for token, label in browsers if token in agent), "")
    return " · ".join(part for part in (system, browser) if part)[:80]


# --------------------------------------------------------------------------
# Creating a passkey
# --------------------------------------------------------------------------


def registration_options(request, user):
    rp_id, _origin = _relying_party(request)
    options = generate_registration_options(
        rp_id=rp_id,
        rp_name=ContestSettings.load().contest_name[:64],
        user_id=str(user.pk).encode(),
        user_name=user.email,
        user_display_name=user.full_name or user.email,
        # A "discoverable" passkey: the device remembers which account it is
        # for, so signing in needs no email address. The device must also
        # check it is really its owner (fingerprint, face or PIN).
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=base64url_to_bytes(key.credential_id))
            for key in user.passkeys.all()
        ],
    )
    _remember(request, "register", options.challenge, user.pk)
    return json.loads(options_to_json(options))


def register(request, user, credential):
    challenge = _recall(request, "register", user.pk)
    rp_id, origin = _relying_party(request)
    try:
        verified = verify_registration_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=rp_id,
            expected_origin=origin,
            require_user_verification=True,
        )
    except (WebAuthnException, ValueError, KeyError, TypeError) as exc:
        raise PasskeyError("invalid") from exc
    credential_id = bytes_to_base64url(verified.credential_id)
    if Passkey.objects.filter(credential_id=credential_id).exists():
        raise PasskeyError("duplicate")
    return Passkey.objects.create(
        user=user,
        credential_id=credential_id,
        public_key=verified.credential_public_key,
        sign_count=verified.sign_count,
        name=device_name(request),
    )


# --------------------------------------------------------------------------
# Signing in with one
# --------------------------------------------------------------------------


def authentication_options(request):
    rp_id, _origin = _relying_party(request)
    options = generate_authentication_options(
        rp_id=rp_id, user_verification=UserVerificationRequirement.REQUIRED
    )
    _remember(request, "authenticate", options.challenge)
    return json.loads(options_to_json(options))


def authenticate(request, credential):
    """Return the user a signed answer belongs to, or raise PasskeyError."""
    challenge = _recall(request, "authenticate")
    rp_id, origin = _relying_party(request)
    try:
        credential_id = credential["id"] if isinstance(credential, dict) else ""
    except (KeyError, TypeError):
        credential_id = ""
    key = (
        Passkey.objects.select_related("user").filter(credential_id=credential_id).first()
        if isinstance(credential_id, str) and credential_id
        else None
    )
    if key is None or not key.user.is_active:
        raise PasskeyError("unknown")
    try:
        verified = verify_authentication_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=rp_id,
            expected_origin=origin,
            credential_public_key=bytes(key.public_key),
            credential_current_sign_count=key.sign_count,
            require_user_verification=True,
        )
    except (WebAuthnException, ValueError, KeyError, TypeError) as exc:
        raise PasskeyError("invalid") from exc
    key.sign_count = verified.new_sign_count
    key.last_used_at = timezone.now()
    key.save(update_fields=["sign_count", "last_used_at"])
    return key.user
