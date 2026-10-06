"""Everything a judge can see. Nothing here may expose an author's identity,
the original file or filename, or who else is reading the same essay."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from .. import contest
from ..forms import OnboardingForm, ScoreSheetForm
from ..models import (
    CRITERIA_KEYS,
    Assignment,
    ContestSettings,
    Essay,
    JudgeAttestation,
    Prompt,
    Referral,
    ScoreSheet,
)
from ..rubric import LEVEL_UPPER_BOUNDS, criterion_name, get_rubric
from ..services import audit, emails, pdf
from ..services.text import count_words
from .common import judge_required


def _my_assignments(user):
    return (
        Assignment.objects.filter(
            judge=user,
            status__in=Assignment.ACTIVE_STATUSES,
            essay__status=Essay.STATUS_APPROVED,
        )
        .select_related("essay", "essay__prompt", "sheet")
        .order_by("assigned_at", "id")
    )


def _get_assignment(request, code):
    assignment = _my_assignments(request.user).filter(essay__code=code).first()
    if assignment is None:
        raise Http404
    return assignment


def _contest_brief():
    """What contestants were asked to do, for the judge's reference."""
    config = ContestSettings.load()
    return {
        "brief": contest.brief(config.word_limit),
        "prompts": Prompt.objects.filter(is_active=True),
    }


@login_required
def onboarding(request):
    """The signed statement every judge completes before reading any essay."""
    if not request.user.is_judge:
        raise PermissionDenied
    if request.user.is_onboarded:
        return redirect("judge_dashboard")
    form = OnboardingForm(request.POST or None, initial={"signed_name": ""})
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            attestation = JudgeAttestation.objects.create(
                user=request.user,
                signed_name=form.cleaned_data["signed_name"].strip(),
                conflict_notes=form.cleaned_data["conflict_notes"].strip(),
                ip=audit.client_ip(request),
            )
            attestation.conflict_prompts.set(form.cleaned_data["conflict_prompts"])
        audit.log(
            request,
            "statement_signed",
            detail=", ".join(str(p) for p in form.cleaned_data["conflict_prompts"]),
        )
        messages.success(request, _("Thank you. You can now begin judging."))
        return redirect("judge_dashboard")
    return render(
        request,
        "portal/judge/onboarding.html",
        {
            "form": form,
            "rubric": get_rubric(),
            **_contest_brief(),
            "has_prompts": Prompt.objects.filter(is_active=True).exists(),
        },
    )


@judge_required
def dashboard(request):
    config = ContestSettings.load()
    assignments = list(_my_assignments(request.user))
    todo = [a for a in assignments if a.is_pending]
    done = [a for a in assignments if a.status == Assignment.STATUS_SUBMITTED]
    rounds = {a.round for a in todo}
    only_rescores = bool(rounds) and Assignment.ROUND_INITIAL not in rounds
    deadline = config.deadline_for(
        Assignment.ROUND_RESCORE if only_rescores else Assignment.ROUND_INITIAL
    )
    total = len(assignments)
    return render(
        request,
        "portal/judge/dashboard.html",
        {
            "todo": todo,
            "done": done,
            "total": total,
            "percent": round(100 * len(done) / total) if total else 0,
            "deadline": deadline,
            "overdue": bool(deadline and todo and timezone.now() > deadline),
        },
    )


@judge_required
def rubric(request):
    return render(request, "portal/judge/rubric.html", {"rubric": get_rubric(), **_contest_brief()})


def submission_problems(sheet, config):
    """Why this sheet cannot be submitted yet (empty list when it can)."""
    problems = []
    missing = [criterion_name(key) for key in CRITERIA_KEYS if getattr(sheet, key) is None]
    if missing:
        problems.append(
            _("Score every criterion. Missing: %(list)s.") % {"list": ", ".join(missing)}
        )
    uncommented = [
        criterion_name(key) for key in CRITERIA_KEYS if not getattr(sheet, f"{key}_comment").strip()
    ]
    if uncommented:
        problems.append(
            _("Write a justification for every criterion. Missing: %(list)s.")
            % {"list": ", ".join(uncommented)}
        )
    words = sum(count_words(text) for text in sheet.comment_texts())
    if words < config.min_comment_words:
        problems.append(
            _("Your comments total %(words)s words; at least %(minimum)s are required.")
            % {"words": words, "minimum": config.min_comment_words}
        )
    flagged = sheet.plagiarism_suspected or sheet.refer_ai_markers or sheet.refer_other
    if flagged and not sheet.flag_notes.strip():
        problems.append(
            _("Explain the flag or referral in the notes: identify the passage(s) and your reason.")
        )
    if not sheet.confirmed or not sheet.signature.strip():
        problems.append(_("Tick the confirmation and type your name to sign the sheet."))
    return problems


def _save_draft(assignment, form):
    sheet = form.save(commit=False)
    sheet.assignment = assignment
    sheet.save()
    if assignment.status == Assignment.STATUS_ASSIGNED:
        assignment.status = Assignment.STATUS_DRAFT
        assignment.started_at = timezone.now()
        assignment.save(update_fields=["status", "started_at"])
    return sheet


def _raise_referrals(assignment, sheet):
    wanted = []
    if sheet.refer_ai_markers:
        wanted.append(Referral.KIND_AI)
    if sheet.refer_other:
        wanted.append(Referral.KIND_OTHER)
    if sheet.plagiarism_suspected:
        wanted.append(Referral.KIND_PLAGIARISM)
    for kind in wanted:
        if assignment.referrals.filter(kind=kind, resolved_at__isnull=True).exists():
            continue
        referral = Referral.objects.create(assignment=assignment, kind=kind, notes=sheet.flag_notes)
        emails.notify_admins_of_referral(referral)


def _lock_for_write(assignment):
    """Lock the assignment row and re-read its status.

    Call inside transaction.atomic(). Without this, an autosave already in
    flight could land just after the judge pressed Submit (or after an admin
    removed the assignment) and alter a sheet that is meant to be final.
    Returns (writable, sheet).
    """
    status = (
        Assignment.objects.select_for_update()
        .filter(pk=assignment.pk)
        .values_list("status", flat=True)
        .first()
    )
    assignment.status = status
    current = ScoreSheet.objects.filter(assignment=assignment).first()
    return status in Assignment.PENDING_STATUSES, current or ScoreSheet(assignment=assignment)


def _handle_sheet_post(request, assignment, config):
    """Save a draft or submit. Returns (response_or_None, form, sheet, problems)."""
    with transaction.atomic():
        writable, instance = _lock_for_write(assignment)
        if not writable:
            raise PermissionDenied
        form = ScoreSheetForm(request.POST, instance=instance)
        if not form.is_valid():
            return None, form, instance, []
        instance = _save_draft(assignment, form)
        if request.POST.get("action") != "submit":
            messages.success(request, _("Draft saved."))
            return redirect("judge_sheet", code=assignment.essay.code), form, instance, []
        problems = submission_problems(instance, config)
        if problems:
            return None, form, instance, problems
        assignment.status = Assignment.STATUS_SUBMITTED
        assignment.submitted_at = timezone.now()
        assignment.save(update_fields=["status", "submitted_at"])
        _raise_referrals(assignment, instance)
        audit.log(request, "sheet_submitted", target=assignment.essay.code)
    messages.success(
        request,
        _("Your sheet for essay %(code)s has been submitted.") % {"code": assignment.essay.code},
    )
    return redirect("judge_dashboard"), form, instance, []


@judge_required
def sheet(request, code):
    """Read an essay and fill in its judging sheet."""
    assignment = _get_assignment(request, code)
    config = ContestSettings.load()
    instance = getattr(assignment, "sheet", None) or ScoreSheet(assignment=assignment)
    locked = assignment.status == Assignment.STATUS_SUBMITTED
    problems = []

    form = ScoreSheetForm(instance=instance)
    if request.method == "POST":
        if locked:
            raise PermissionDenied
        response, form, instance, problems = _handle_sheet_post(request, assignment, config)
        if response is not None:
            return response

    rubric_data = get_rubric()
    criteria = [
        {
            **criterion,
            "score": form[criterion["key"]],
            "comment": form[f"{criterion['key']}_comment"],
        }
        for criterion in rubric_data["criteria"]
    ]
    essay = assignment.essay
    return render(
        request,
        "portal/judge/sheet.html",
        {
            "assignment": assignment,
            "essay": essay,
            "pages": range(1, essay.released_pages + 1),
            "text_pages": essay.released_text.split("\f") if essay.released_text else [],
            "form": form,
            "sheet": instance,
            "criteria": criteria,
            "rubric": rubric_data,
            "locked": locked,
            "problems": problems,
            "min_words": config.min_comment_words,
            "level_bounds": LEVEL_UPPER_BOUNDS,
            "deadline": config.deadline_for(assignment.round),
        },
    )


@judge_required
def page(request, code, number):
    """One page of an assigned essay, as an image with redactions burned in.

    Served from the released copy only: there is no path from here to the
    original file or to the unredacted renders.
    """
    assignment = _get_assignment(request, code)
    essay = assignment.essay
    if not 1 <= number <= essay.released_pages:
        raise Http404
    try:
        path = pdf.released_page(essay.release_dir, number)
        return FileResponse(open(path, "rb"), content_type="image/png")  # noqa: SIM115
    except (OSError, pdf.PdfError) as exc:
        raise Http404 from exc


@judge_required
@require_POST
def autosave(request, code):
    assignment = _get_assignment(request, code)
    with transaction.atomic():
        writable, instance = _lock_for_write(assignment)
        if not writable:
            return JsonResponse({"ok": False, "error": "locked"}, status=409)
        form = ScoreSheetForm(request.POST, instance=instance)
        if not form.is_valid():
            return JsonResponse({"ok": False, "error": "invalid"}, status=400)
        _save_draft(assignment, form)
    return JsonResponse({"ok": True, "saved_at": timezone.localtime().strftime("%H:%M")})


@judge_required
@require_POST
def recuse(request, code):
    """Hand an essay back because the judge cannot read it impartially."""
    assignment = _get_assignment(request, code)
    if assignment.status == Assignment.STATUS_SUBMITTED:
        raise PermissionDenied
    reason = request.POST.get("reason", "").strip()
    if not reason:
        messages.error(request, _("Please give a short reason for the committee chair."))
        return redirect("judge_sheet", code=code)
    with transaction.atomic():
        writable, _sheet = _lock_for_write(assignment)
        if not writable:
            raise PermissionDenied
        assignment.status = Assignment.STATUS_RECUSED
        assignment.closed_reason = reason
        assignment.save(update_fields=["status", "closed_reason"])
        referral = Referral.objects.create(
            assignment=assignment, kind=Referral.KIND_STANDPOINT, notes=reason
        )
    emails.notify_admins_of_referral(referral)
    audit.log(request, "judge_recused", target=assignment.essay.code)
    messages.success(
        request,
        _("Essay %(code)s has been returned to the committee chair for reassignment.")
        % {"code": assignment.essay.code},
    )
    return redirect("judge_dashboard")
