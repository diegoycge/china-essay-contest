"""Committee (admin) pages."""

import json

from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Max, Q
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from django.views.decorators.http import require_POST

from .. import contest
from ..forms import (
    EssayMetaForm,
    InviteForm,
    PromptForm,
    SettingsForm,
    UploadForm,
    UserEditForm,
)
from ..models import (
    DIVISION_CHOICES,
    Assignment,
    AuditLog,
    ContestSettings,
    EmailLog,
    Essay,
    JudgeAttestation,
    Prompt,
    Referral,
    User,
)
from ..labels import failure_text, problem_text
from ..rubric import get_rubric
from ..services import anonymize as anon
from ..services import assignment as assigner
from ..services import audit, emails, exports, intake, pdf, redaction, scoring
from ..services.text import count_words
from .common import admin_required, paginate


def _posted_id(request, name):
    """A numeric id from a form field; anything else is a 404, not a crash."""
    value = request.POST.get(name, "")
    if not value.isdigit():
        raise Http404
    return int(value)


# --------------------------------------------------------------------------
# Dashboard
# --------------------------------------------------------------------------


def judge_progress(config):
    now = timezone.now()
    judges = (
        User.objects.filter(role=User.ROLE_JUDGE)
        .select_related("attestation")
        .annotate(last_activity=Max("assignments__sheet__updated_at"))
    )
    rows = []
    counts = {}
    for row in (
        Assignment.objects.filter(essay__status=Essay.STATUS_APPROVED)
        .values("judge_id", "status", "round")
        .annotate(n=Count("id"))
    ):
        counts.setdefault(row["judge_id"], []).append(row)
    for judge in judges:
        tally = {"assigned": 0, "draft": 0, "submitted": 0}
        overdue = 0
        for row in counts.get(judge.id, []):
            if row["status"] in tally:
                tally[row["status"]] += row["n"]
            deadline = config.deadline_for(row["round"])
            if row["status"] in Assignment.PENDING_STATUSES and deadline and now > deadline:
                overdue += row["n"]
        total = sum(tally.values())
        rows.append(
            {
                "judge": judge,
                "total": total,
                "not_started": tally["assigned"],
                "draft": tally["draft"],
                "submitted": tally["submitted"],
                "outstanding": tally["assigned"] + tally["draft"],
                "overdue": overdue,
                "percent": round(100 * tally["submitted"] / total) if total else 0,
                "last_activity": max(
                    [d for d in (judge.last_activity, judge.last_login) if d], default=None
                ),
            }
        )
    rows.sort(
        key=lambda r: (not r["judge"].is_active, -r["outstanding"], r["judge"].full_name.lower())
    )
    return rows


@admin_required
def dashboard(request):
    config = ContestSettings.load()
    status_counts = dict(Essay.objects.values_list("status").annotate(n=Count("id")))
    summaries = scoring.summarize_all(config)
    progress = judge_progress(config)
    active_total = sum(len(s.active) for s in summaries)
    submitted_total = sum(len(s.submitted) for s in summaries)
    open_slots = sum(s.missing_readers for s in summaries)
    now = timezone.now()

    divisions = []
    for value, label in DIVISION_CHOICES:
        rows = [s for s in summaries if s.essay.division == value]
        divisions.append(
            {
                "label": label,
                "released": len(rows),
                "complete": sum(1 for s in rows if s.complete),
                "percent": round(100 * sum(1 for s in rows if s.complete) / len(rows))
                if rows
                else 0,
            }
        )

    return render(
        request,
        "portal/manage/dashboard.html",
        {
            "total_essays": sum(status_counts.values()),
            "needs_review": status_counts.get(Essay.STATUS_REVIEW, 0),
            "failed": status_counts.get(Essay.STATUS_FAILED, 0),
            "released": status_counts.get(Essay.STATUS_APPROVED, 0),
            "disqualified": status_counts.get(Essay.STATUS_DISQUALIFIED, 0)
            + status_counts.get(Essay.STATUS_WITHDRAWN, 0),
            "open_slots": open_slots,
            "essays_missing_readers": sum(1 for s in summaries if s.missing_readers),
            "active_total": active_total,
            "submitted_total": submitted_total,
            "percent": round(100 * submitted_total / active_total) if active_total else 0,
            "complete_essays": sum(1 for s in summaries if s.complete),
            "needs_rescore": sum(1 for s in summaries if s.needs_rescore),
            "open_referrals": Referral.objects.filter(resolved_at__isnull=True).count(),
            "unsigned_judges": sum(
                1 for r in progress if r["judge"].is_active and not r["judge"].is_onboarded
            ),
            "overdue_total": sum(r["overdue"] for r in progress),
            "progress": progress,
            "divisions": divisions,
            "deadline": config.initial_deadline,
            "rescore_deadline": config.rescore_deadline,
            "deadline_passed": bool(config.initial_deadline and now > config.initial_deadline),
            "unnotified": emails.unannounced_assignments().count(),
        },
    )


# --------------------------------------------------------------------------
# Essays
# --------------------------------------------------------------------------


@admin_required
def essays(request):
    config = ContestSettings.load()
    queryset = Essay.objects.select_related("prompt")
    status = request.GET.get("status", "")
    division = request.GET.get("division", "")
    prompt = request.GET.get("prompt", "")
    query = request.GET.get("q", "").strip()
    if status:
        queryset = queryset.filter(status=status)
    if division:
        queryset = queryset.filter(division=division)
    if prompt.isdigit():
        queryset = queryset.filter(prompt_id=int(prompt))
    if query:
        queryset = queryset.filter(
            Q(code__icontains=query)
            | Q(author_name__icontains=query)
            | Q(author_school__icontains=query)
            | Q(author_email__icontains=query)
            | Q(original_filename__icontains=query)
        )
    page = paginate(request, queryset.order_by("-uploaded_at", "-id"))
    summaries = scoring.summarize_all(config, Essay.objects.filter(pk__in=[e.pk for e in page]))
    by_id = {s.essay.id: s for s in summaries}
    rows = [{"essay": essay, "summary": by_id.get(essay.id)} for essay in page]
    params = request.GET.copy()
    params.pop("page", None)
    return render(
        request,
        "portal/manage/essays.html",
        {
            "page": page,
            "rows": rows,
            "status_choices": Essay.STATUS_CHOICES,
            "division_choices": DIVISION_CHOICES,
            "prompts": Prompt.objects.all(),
            "filters": {"status": status, "division": division, "prompt": prompt, "q": query},
            "querystring": params.urlencode(),
        },
    )


def _upload_message(outcome, essay):
    if outcome == "created":
        return _("Uploaded as %(code)s — ready for anonymization review.") % {"code": essay.code}
    if outcome == "created_unmatched":
        return _(
            "Uploaded as %(code)s. Another upload has the same file name, so no author record "
            "was attached — enter the author’s details by hand before reviewing."
        ) % {"code": essay.code}
    if outcome == "failed":
        return _("Stored as %(code)s, but it could not be processed: %(note)s") % {
            "code": essay.code,
            "note": failure_text(essay.extraction_note),
        }
    return _("Skipped: identical to %(code)s, which is already in the portal.") % {
        "code": essay.code
    }


def _intake_error_message(error):
    return {
        "unsupported": _("Only PDF files are accepted."),
        "too_large": _("File is larger than %(mb)s MB.") % {"mb": settings.MAX_ESSAY_FILE_MB},
        "empty": _("The spreadsheet has no data rows."),
        "sheet_unsupported": _("Use a CSV or XLSX file for the author spreadsheet."),
        "sheet_unreadable": _("The spreadsheet could not be read."),
        "sheet_too_large": _("The spreadsheet is too large."),
        "no_filename_column": _("The spreadsheet needs a column named “filename”."),
    }.get(str(error), str(error))


@admin_required
def upload(request):
    form = UploadForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        # Plain form post (no JavaScript): handle every file in one request.
        results = []
        for upload_file in request.FILES.getlist("files"):
            results.append(_handle_upload(request, upload_file, form))
        created = sum(1 for r in results if r["outcome"].startswith("created"))
        messages.success(
            request,
            ngettext("%(n)s essay uploaded.", "%(n)s essays uploaded.", created) % {"n": created},
        )
        for result in results:
            if result["outcome"] != "created":
                messages.warning(request, f"{result['name']}: {result['message']}")
        return redirect("manage_review_queue")
    return render(
        request,
        "portal/manage/upload.html",
        {
            "form": form,
            "max_mb": settings.MAX_ESSAY_FILE_MB,
            "records": intake.IntakeRecord.objects.count(),
        },
    )


def _handle_upload(request, upload_file, form):
    try:
        essay, outcome = intake.create_essay_from_upload(
            upload_file,
            division=form.cleaned_data["division"],
            prompt=form.cleaned_data["prompt"],
            user=request.user,
        )
    except intake.IntakeError as error:
        return {
            "name": upload_file.name,
            "outcome": "error",
            "message": _intake_error_message(error),
        }
    if outcome != "duplicate":
        audit.log(request, "essay_uploaded", target=essay.code, detail=essay.original_filename)
    return {
        "name": upload_file.name,
        "outcome": outcome,
        "code": essay.code,
        "message": _upload_message(outcome, essay),
    }


@admin_required
@require_POST
def upload_file(request):
    """One file per request, so the page can show progress for large batches."""
    form = UploadForm(request.POST)
    upload_file = request.FILES.get("file")
    if not form.is_valid() or upload_file is None:
        return JsonResponse({"outcome": "error", "message": _("Invalid request.")}, status=400)
    return JsonResponse(_handle_upload(request, upload_file, form))


@admin_required
@require_POST
def import_metadata(request):
    sheet = request.FILES.get("sheet")
    if sheet is None:
        messages.error(request, _("Choose a CSV or XLSX file first."))
        return redirect("manage_upload")
    try:
        stats = intake.import_metadata(sheet)
    except intake.IntakeError as error:
        messages.error(request, _intake_error_message(error))
        return redirect("manage_upload")
    audit.log(request, "author_records_imported", detail=str(stats))
    messages.success(
        request,
        _(
            "%(rows)s author records imported; %(matched)s matched essays already uploaded "
            "(%(reprocessed)s re-redacted with the new details)."
        )
        % stats,
    )
    if stats["ambiguous"]:
        messages.warning(
            request,
            _(
                "These file names belong to more than one author or more than one upload, so "
                "no author record was attached automatically. Enter the details by hand on "
                "each essay: %(names)s"
            )
            % {"names": ", ".join(stats["ambiguous"][:30])},
        )
    if stats["pulled_back"]:
        messages.warning(
            request,
            _(
                "%(n)s released essays were pulled back for review: the author details just "
                "imported still appear in their text."
            )
            % {"n": stats["pulled_back"]},
        )
    return redirect("manage_upload")


def _assignment_rows(essay):
    return list(essay.assignments.select_related("judge", "sheet").order_by("assigned_at", "id"))


@admin_required
def essay_detail(request, pk):
    essay = get_object_or_404(Essay.objects.select_related("prompt"), pk=pk)
    config = ContestSettings.load()
    form = EssayMetaForm(instance=essay)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "save_meta":
            form = EssayMetaForm(request.POST, instance=essay)
            if form.is_valid():
                essay = form.save(commit=False)
                # Saving here is the admin vouching for the author details, which
                # settles any doubt left by a shared file name.
                essay.flags = [f for f in essay.flags if f.get("kind") != "duplicate_filename"]
                if essay.work_dir:
                    identity_changed = any(
                        field in form.changed_data
                        for field in ("author_name", "author_email", "author_school")
                    )
                    if essay.status == Essay.STATUS_REVIEW:
                        intake.run_auto_redaction(essay)  # redact the corrected name
                    elif (
                        essay.status == Essay.STATUS_APPROVED
                        and identity_changed
                        and anon.hard_leaks(
                            essay.released_text,
                            essay.author_name,
                            essay.author_email,
                            essay.author_school,
                        )
                    ):
                        # The corrected name is on pages judges can already see.
                        essay.status = Essay.STATUS_REVIEW
                        intake.run_auto_redaction(essay)
                        messages.warning(
                            request,
                            _(
                                "The essay was pulled back from judges. Check it and release it again."
                            ),
                        )
                    else:
                        intake.recompute(essay)
                essay.save()
                audit.log(request, "essay_details_edited", target=essay.code)
                messages.success(request, _("Essay details saved."))
                return redirect("manage_essay", pk=essay.pk)
        elif action == "assign":
            _assign_from_post(request, essay)
            return redirect("manage_essay", pk=essay.pk)
        elif action == "remove_assignment":
            row = get_object_or_404(Assignment, pk=_posted_id(request, "assignment"), essay=essay)
            row.status = Assignment.STATUS_REMOVED
            row.closed_reason = request.POST.get("reason", "").strip()
            row.save(update_fields=["status", "closed_reason"])
            audit.log(request, "assignment_removed", target=essay.code, detail=row.judge.email)
            messages.success(request, _("Assignment removed. Any scores it held no longer count."))
            return redirect("manage_essay", pk=essay.pk)
        elif action == "status":
            _change_status(request, essay, request.POST.get("status"))
            return redirect("manage_essay", pk=essay.pk)
        elif action == "finalist":
            _toggle_finalist(request, essay)
            return redirect("manage_essay", pk=essay.pk)
        elif action == "delete":
            if essay.assignments.exists():
                messages.error(
                    request,
                    _("This essay has assignments and cannot be deleted. Withdraw it instead."),
                )
                return redirect("manage_essay", pk=essay.pk)
            audit.log(request, "essay_deleted", target=essay.code, detail=essay.original_filename)
            intake.delete_files(essay)
            essay.delete()
            messages.success(request, _("Essay deleted."))
            return redirect("manage_essays")

    rows = _assignment_rows(essay)
    summary = scoring.summarize(essay, config, rows)
    return render(
        request,
        "portal/manage/essay_detail.html",
        {
            "essay": essay,
            "form": form,
            "assignments": rows,
            "summary": summary,
            "candidates": assigner.candidates_for(essay) if essay.is_judgeable else [],
            "open_referrals": Referral.objects.filter(
                assignment__essay=essay, resolved_at__isnull=True
            ),
        },
    )


def _assign_from_post(request, essay, round_=None):
    if not essay.is_judgeable:
        messages.error(request, _("Only essays released to judges can be assigned."))
        return None
    round_ = round_ or request.POST.get("round") or Assignment.ROUND_INITIAL
    if round_ not in dict(Assignment.ROUND_CHOICES):
        round_ = Assignment.ROUND_INITIAL
    judge = None
    if request.POST.get("judge"):
        judge = get_object_or_404(
            User, pk=_posted_id(request, "judge"), role=User.ROLE_JUDGE, is_active=True
        )
    try:
        row = assigner.assign(essay, judge, round_=round_, actor=request.user)
    except assigner.NoEligibleJudge:
        messages.error(
            request,
            _(
                "No eligible judge is available for %(code)s. Every judge who has signed the "
                "statement has either read it already, declared a conflict with its prompt, or "
                "reached their limit."
            )
            % {"code": essay.code},
        )
        return None
    audit.log(
        request, "assignment_created", target=essay.code, detail=f"{row.judge.email} ({round_})"
    )
    if request.POST.get("notify"):
        emails.notify_new_assignments([row])
    messages.success(
        request,
        _("%(code)s assigned to %(judge)s.") % {"code": essay.code, "judge": row.judge.full_name},
    )
    return row


def _change_status(request, essay, status):
    allowed = {
        Essay.STATUS_WITHDRAWN: _("Essay withdrawn. Judges can no longer see it."),
        Essay.STATUS_DISQUALIFIED: _("Essay disqualified. Judges can no longer see it."),
        "restore": _("Essay restored."),
    }
    if status not in allowed:
        return
    if status == "restore":
        essay.status = Essay.STATUS_APPROVED if essay.approved_at else Essay.STATUS_REVIEW
    else:
        essay.status = status
        essay.is_finalist = False
    essay.save(update_fields=["status", "is_finalist"])
    audit.log(request, "essay_status_changed", target=essay.code, detail=essay.status)
    messages.success(request, allowed[status])


def _toggle_finalist(request, essay):
    essay.is_finalist = not essay.is_finalist
    essay.finalist_confirmed_by = request.user if essay.is_finalist else None
    essay.finalist_confirmed_at = timezone.now() if essay.is_finalist else None
    essay.save(update_fields=["is_finalist", "finalist_confirmed_by", "finalist_confirmed_at"])
    audit.log(
        request,
        "finalist_confirmed" if essay.is_finalist else "finalist_removed",
        target=essay.code,
    )


@admin_required
def original_file(request, pk):
    essay = get_object_or_404(Essay, pk=pk)
    if not essay.original_file:
        raise Http404
    audit.log(request, "original_downloaded", target=essay.code)
    return FileResponse(
        essay.original_file.open("rb"), as_attachment=True, filename=essay.original_filename
    )


# --------------------------------------------------------------------------
# Anonymization review
# --------------------------------------------------------------------------


def _review_queue():
    return Essay.objects.filter(status__in=(Essay.STATUS_REVIEW, Essay.STATUS_FAILED)).order_by(
        "uploaded_at", "id"
    )


@admin_required
def review_queue(request):
    first = _review_queue().first()
    if first is None:
        messages.info(request, _("No essays are waiting for anonymization review."))
        return redirect("manage_essays")
    return redirect("manage_review", pk=first.pk)


def _png(path):
    try:
        return FileResponse(open(path, "rb"), content_type="image/png")  # noqa: SIM115
    except (OSError, pdf.PdfError) as exc:
        raise Http404 from exc


@admin_required
def work_page(request, pk, number):
    """An unredacted page image, for the review screen. Admins only."""
    essay = get_object_or_404(Essay, pk=pk)
    if not 1 <= number <= essay.page_count:
        raise Http404
    try:
        return _png(pdf.work_page(essay.work_dir, number))
    except pdf.PdfError as exc:
        raise Http404 from exc


@admin_required
def released_page(request, pk, number):
    """A page exactly as judges get it, for the admin's preview."""
    essay = get_object_or_404(Essay, pk=pk)
    if not 1 <= number <= essay.released_pages:
        raise Http404
    try:
        return _png(pdf.released_page(essay.release_dir, number))
    except pdf.PdfError as exc:
        raise Http404 from exc


@admin_required
def preview(request, pk):
    """What judges see for a released essay: the pages and the copyable text."""
    essay = get_object_or_404(Essay.objects.select_related("prompt"), pk=pk)
    if not essay.release_dir:
        messages.info(request, _("This essay has not been released yet."))
        return redirect("manage_review", pk=essay.pk)
    return render(
        request,
        "portal/manage/preview.html",
        {
            "essay": essay,
            "pages": range(1, essay.released_pages + 1),
            "text_pages": essay.released_text.split("\f"),
        },
    )


def _apply_posted_state(request, essay):
    """Take the boxes and dropped pages sent by the review screen.

    Returns True if they differ from what is stored. The essay is updated in
    memory only; the caller decides whether to save.
    """
    raw = request.POST.get("state")
    if not raw or not essay.work_dir:
        return False
    try:
        state = json.loads(raw)
    except ValueError:
        return False
    if not isinstance(state, dict):
        return False
    boxes = redaction.clean(state.get("redactions"), essay.page_count)
    dropped = sorted(
        {
            page
            for page in state.get("dropped") or []
            if isinstance(page, int) and 0 <= page < essay.page_count
        }
    )

    def canonical(items):
        return sorted(json.dumps(item, sort_keys=True) for item in items)

    changed = canonical(boxes) != canonical(essay.redactions) or dropped != sorted(
        essay.dropped_pages
    )
    essay.redactions, essay.dropped_pages = boxes, dropped
    return changed


def _blocking_problems(request, essay):
    """Release problems that stand, given whether the reviewer ticked override."""
    problems = intake.release_problems(essay)
    if request.POST.get("override"):
        problems = [code for code in problems if code in intake.HARD_PROBLEMS]
    return problems


@admin_required
def review(request, pk):
    essay = get_object_or_404(Essay.objects.select_related("prompt"), pk=pk)
    queue = _review_queue()

    if request.method == "POST":
        action = request.POST.get("action")
        here = redirect("manage_review", pk=essay.pk)

        if action == "retry" and essay.status == Essay.STATUS_FAILED and essay.original_file:
            try:
                essay.work_dir = pdf.render(essay.original_file.path)
                layout = pdf.load_layout(essay.work_dir)
                essay.page_count = len(layout["pages"])
                essay.meta_authors = intake.clean_meta_authors(layout.get("authors", []))
                essay.status, essay.extraction_note = Essay.STATUS_REVIEW, ""
                intake.run_auto_redaction(essay, reset=True)
                messages.success(request, _("The file was processed."))
            except pdf.PdfError as exc:
                essay.extraction_note = str(exc)[:300]
                messages.error(request, failure_text(essay.extraction_note))
            essay.save()
            return here
        if not essay.work_dir:
            return here

        if action == "unrelease" and essay.status == Essay.STATUS_APPROVED:
            essay.status = Essay.STATUS_REVIEW
            essay.save(update_fields=["status"])
            audit.log(request, "essay_unreleased", target=essay.code)
            messages.success(
                request, _("Essay pulled back. Judges cannot see it until it is released again.")
            )
            return here

        if action == "rerun":
            was_live = essay.status == Essay.STATUS_APPROVED
            intake.run_auto_redaction(essay, reset=True)
            messages.success(request, _("Automatic redaction re-run. Your own boxes were removed."))
            if was_live:
                # The fresh redactions have not been reviewed by anyone yet.
                essay.status = Essay.STATUS_REVIEW
                messages.warning(
                    request,
                    _("The essay was pulled back from judges. Check it and release it again."),
                )
            essay.save()
            audit.log(request, "redaction_rerun", target=essay.code)
            return here

        if action in ("save", "approve", "term"):
            changed = _apply_posted_state(request, essay)
            term = request.POST.get("term", "").strip()[:60]
            if action == "term" and term:
                layout = pdf.load_layout(essay.work_dir)
                found = redaction.term_redactions(layout, term, set(essay.dropped_pages))
                essay.redactions = essay.redactions + found
                changed = changed or bool(found)
                if found:
                    messages.success(
                        request,
                        ngettext(
                            "“%(term)s” redacted in %(n)s place.",
                            "“%(term)s” redacted in %(n)s places.",
                            len(found),
                        )
                        % {"term": term, "n": len(found)},
                    )
                else:
                    messages.info(
                        request, _("“%(term)s” does not appear on the pages.") % {"term": term}
                    )
            if changed:
                intake.recompute(essay)
                audit.log(request, "redactions_edited", target=essay.code)

            live = essay.status == Essay.STATUS_APPROVED
            releasing = action == "approve" and essay.status == Essay.STATUS_REVIEW
            if releasing or (live and changed):
                # Judges see the result the moment it is written, so a change to
                # a released essay has to pass the same checks as a release.
                problems = _blocking_problems(request, essay)
                if problems:
                    messages.error(
                        request,
                        (_("Not released: %(why)s.") if releasing else _("Not saved: %(why)s."))
                        % {"why": problem_text(problems)},
                    )
                    if releasing:
                        essay.save()  # keep the reviewer's boxes; the essay stays in review
                    return here
                previous = intake.write_release(essay)
                if releasing:
                    essay.status = Essay.STATUS_APPROVED
                    essay.approved_by = request.user
                    essay.approved_at = timezone.now()
                essay.save()
                pdf.remove_dir("released", previous)
                if releasing:
                    overridden = intake.release_problems(essay)
                    audit.log(
                        request,
                        "essay_released",
                        target=essay.code,
                        detail="override: " + ",".join(overridden) if overridden else "",
                    )
                    messages.success(
                        request, _("%(code)s released for judging.") % {"code": essay.code}
                    )
                    following = queue.exclude(pk=essay.pk).first()
                    return (
                        redirect("manage_review", pk=following.pk)
                        if following
                        else redirect("manage_essays")
                    )
                messages.success(request, _("Saved. Judges now see the updated pages."))
                return here
            essay.save()
            if action == "save":
                messages.success(request, _("Saved."))
            return here
        return here

    ids = list(queue.values_list("pk", flat=True))
    position, next_id = None, None
    if essay.pk in ids:
        index = ids.index(essay.pk)
        position = index + 1
        others = ids[index + 1 :] + ids[:index]
        next_id = others[0] if others else None
    elif ids:
        next_id = ids[0]
    dropped = set(essay.dropped_pages)
    return render(
        request,
        "portal/manage/review.html",
        {
            "essay": essay,
            "queue_total": len(ids),
            "position": position,
            "next_id": next_id,
            "pages": [
                {"number": n + 1, "index": n, "dropped": n in dropped}
                for n in range(essay.page_count)
            ],
            "state": {"redactions": essay.redactions, "dropped": sorted(dropped)},
            "text_pages": essay.released_text.split("\f") if essay.released_text else [],
            "problems": problem_text(intake.release_problems(essay)) if essay.work_dir else "",
            "started": essay.assignments.filter(status__in=Assignment.ACTIVE_STATUSES).exists(),
        },
    )


# --------------------------------------------------------------------------
# People
# --------------------------------------------------------------------------


@admin_required
def users(request):
    form = InviteForm(request.POST or None, initial={"role": User.ROLE_JUDGE})
    if request.method == "POST" and form.is_valid():
        user = form.save(commit=False)
        user.set_unusable_password()
        user.save()
        message = emails.issue_invite(user, created_by=request.user)
        audit.log(request, "user_invited", target=user.email, detail=user.role)
        request.session["last_link"] = message.for_session("invite")
        messages.success(request, _("%(name)s has been invited.") % {"name": user.full_name})
        return redirect("manage_users")

    progress = {row["judge"].id: row for row in judge_progress(ContestSettings.load())}
    people = list(User.objects.select_related("attestation").order_by("role", "full_name"))
    for person in people:
        person.progress = progress.get(person.id)
    return render(
        request,
        "portal/manage/users.html",
        {
            "form": form,
            "judges": [p for p in people if p.is_judge],
            "admins": [p for p in people if p.is_admin],
            "last_link": request.session.pop("last_link", None),
        },
    )


@admin_required
def user_detail(request, pk):
    person = get_object_or_404(User, pk=pk)
    form = UserEditForm(instance=person)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "save":
            form = UserEditForm(request.POST, instance=person)
            if form.is_valid():
                form.save()
                audit.log(request, "user_edited", target=person.email)
                messages.success(request, _("Saved."))
                return redirect("manage_user", pk=person.pk)
        elif action == "invite":
            message = emails.issue_invite(person, created_by=request.user)
            audit.log(request, "invite_reissued", target=person.email)
            request.session["last_link"] = message.for_session("invite")
            return redirect("manage_user", pk=person.pk)
        elif action == "reset":
            message = emails.issue_password_reset(person, created_by=request.user)
            audit.log(request, "reset_link_issued", target=person.email)
            request.session["last_link"] = message.for_session("reset")
            return redirect("manage_user", pk=person.pk)
        elif action == "clear_passkeys":
            removed, _detail = person.passkeys.all().delete()
            audit.log(request, "passkeys_cleared", target=person.email, detail=str(removed))
            messages.success(
                request,
                _("Passkeys removed. Create a sign-in link so they can set up a new one."),
            )
            return redirect("manage_user", pk=person.pk)
        elif action == "toggle_active":
            if person == request.user:
                messages.error(request, _("You cannot deactivate your own account."))
            else:
                person.is_active = not person.is_active
                person.save(update_fields=["is_active"])
                audit.log(
                    request,
                    "user_activated" if person.is_active else "user_deactivated",
                    target=person.email,
                )
                messages.success(
                    request,
                    _("Account reactivated.")
                    if person.is_active
                    else _("Account deactivated. Their unfinished essays should be reassigned."),
                )
            return redirect("manage_user", pk=person.pk)
        elif action == "clear_statement":
            JudgeAttestation.objects.filter(user=person).delete()
            audit.log(request, "statement_cleared", target=person.email)
            messages.success(
                request, _("The judge must sign the statement again before continuing.")
            )
            return redirect("manage_user", pk=person.pk)
        elif action == "release_pending":
            released = person.assignments.filter(status__in=Assignment.PENDING_STATUSES).update(
                status=Assignment.STATUS_REMOVED, closed_reason="Released by admin"
            )
            audit.log(
                request, "pending_assignments_released", target=person.email, detail=str(released)
            )
            messages.success(
                request,
                _(
                    "%(n)s unfinished assignments released. Run auto-assign to hand them to other judges."
                )
                % {"n": released},
            )
            return redirect("manage_user", pk=person.pk)

    assignments = (
        person.assignments.select_related("essay", "sheet")
        .exclude(status=Assignment.STATUS_REMOVED)
        .order_by("-assigned_at")
    )
    return render(
        request,
        "portal/manage/user_detail.html",
        {
            "person": person,
            "form": form,
            "attestation": getattr(person, "attestation", None),
            "assignments": assignments,
            "passkey_count": person.passkeys.count(),
            "last_link": request.session.pop("last_link", None),
            "pending_count": sum(1 for a in assignments if a.is_pending),
        },
    )


# --------------------------------------------------------------------------
# Assignment, divergence, referrals
# --------------------------------------------------------------------------


@admin_required
def assignments(request):
    config = ContestSettings.load()
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "auto":
            created, unfilled = assigner.auto_assign(actor=request.user)
            audit.log(
                request, "auto_assigned", detail=f"{len(created)} created, {len(unfilled)} unfilled"
            )
            messages.success(
                request,
                ngettext("%(n)s assignment created.", "%(n)s assignments created.", len(created))
                % {"n": len(created)},
            )
            if unfilled:
                messages.warning(
                    request,
                    _(
                        "%(n)s essays still lack readers because no eligible judge was available: %(codes)s"
                    )
                    % {
                        "n": len(unfilled),
                        "codes": ", ".join(e.code for e, _need in unfilled[:20]),
                    },
                )
            if request.POST.get("notify") and created:
                sent = emails.notify_new_assignments(created)
                messages.info(request, _("%(n)s judges notified by email.") % {"n": sent})
        elif action == "notify":
            sent = emails.notify_new_assignments(list(emails.unannounced_assignments()))
            audit.log(request, "assignment_emails_sent", detail=str(sent))
            messages.success(request, _("%(n)s judges notified by email.") % {"n": sent})
        elif action == "mark_announced":
            count = emails.mark_announced()
            audit.log(request, "assignments_marked_announced", detail=str(count))
            messages.success(request, _("Marked as announced."))
        elif action == "remind":
            sent = emails.send_manual_reminders()
            audit.log(request, "reminders_sent", detail=str(sent))
            messages.success(request, _("Reminder sent to %(n)s judges.") % {"n": sent})
        return redirect("manage_assignments")

    slots = assigner.open_slots(config)
    progress = judge_progress(config)
    return render(
        request,
        "portal/manage/assignments.html",
        {
            "slots": slots[:100],
            "slot_essays": len(slots),
            "slot_total": sum(n for _essay, n in slots),
            "progress": [r for r in progress if r["judge"].is_active],
            "awaiting_release": Essay.objects.filter(status=Essay.STATUS_REVIEW).count(),
            "announce_drafts": []
            if settings.EMAIL_CONFIGURED
            else emails.announcement_drafts(request.user),
            "remind_drafts": []
            if settings.EMAIL_CONFIGURED
            else emails.reminder_drafts(request.user),
            "eligible_judges": assigner.available_judges().count(),
            "unsigned_judges": User.objects.filter(
                role=User.ROLE_JUDGE, is_active=True, attestation__isnull=True
            ).count(),
            "unnotified": emails.unannounced_assignments().count(),
            "outstanding": Assignment.objects.filter(
                status__in=Assignment.PENDING_STATUSES, essay__status=Essay.STATUS_APPROVED
            ).count(),
        },
    )


@admin_required
def divergence(request):
    config = ContestSettings.load()
    if request.method == "POST":
        essay = get_object_or_404(Essay, pk=_posted_id(request, "essay"))
        _assign_from_post(request, essay, round_=Assignment.ROUND_RESCORE)
        return redirect("manage_divergence")

    summaries = [s for s in scoring.summarize_all(config) if s.divergent]
    summaries.sort(key=lambda s: (not s.needs_rescore, -(s.initial_spread or 0)))
    for summary in summaries:
        if summary.needs_rescore:
            summary.candidates = assigner.candidates_for(summary.essay)
    return render(
        request,
        "portal/manage/divergence.html",
        {"summaries": summaries, "threshold": config.divergence_threshold},
    )


@admin_required
def referrals(request):
    if request.method == "POST":
        referral = get_object_or_404(
            Referral.objects.select_related("assignment__essay"), pk=_posted_id(request, "referral")
        )
        action = request.POST.get("action")
        essay = referral.assignment.essay
        note = request.POST.get("note", "").strip()
        with transaction.atomic():
            if action == "disqualify":
                _change_status(request, essay, Essay.STATUS_DISQUALIFIED)
                note = note or "Essay disqualified."
            elif action == "reassign":
                if _assign_from_post(request, essay, round_=referral.assignment.round) is None:
                    return redirect("manage_referrals")
                note = note or "Reassigned to another judge."
            elif action != "dismiss":
                return redirect("manage_referrals")
            referral.resolved_at = timezone.now()
            referral.resolved_by = request.user
            referral.resolution = note or "No action needed."
            referral.save()
        audit.log(request, "referral_resolved", target=essay.code, detail=f"{action}: {note}")
        return redirect("manage_referrals")

    rows = Referral.objects.select_related("assignment__essay", "assignment__judge", "resolved_by")
    return render(
        request,
        "portal/manage/referrals.html",
        {
            "open": [r for r in rows if r.is_open],
            "resolved": [r for r in rows if not r.is_open][:100],
        },
    )


@admin_required
def sheet_view(request, pk):
    """Read-only view of one judge's sheet, with the option to reopen it."""
    row = get_object_or_404(Assignment.objects.select_related("essay", "judge", "sheet"), pk=pk)
    if request.method == "POST" and request.POST.get("action") == "reopen":
        if row.status == Assignment.STATUS_SUBMITTED:
            row.status = Assignment.STATUS_DRAFT
            row.submitted_at = None
            row.save(update_fields=["status", "submitted_at"])
            audit.log(request, "sheet_reopened", target=row.essay.code, detail=row.judge.email)
            messages.success(request, _("Sheet reopened. The judge can edit and resubmit it."))
        return redirect("manage_sheet", pk=row.pk)
    sheet = getattr(row, "sheet", None)
    rubric = get_rubric()
    criteria = []
    for criterion in rubric["criteria"]:
        criteria.append(
            {
                "name": criterion["name"],
                "score": getattr(sheet, criterion["key"]) if sheet else None,
                "comment": getattr(sheet, f"{criterion['key']}_comment") if sheet else "",
            }
        )
    return render(
        request,
        "portal/manage/sheet.html",
        {
            "row": row,
            "sheet": sheet,
            "criteria": criteria,
            "words": sum(count_words(t) for t in sheet.comment_texts()) if sheet else 0,
        },
    )


# --------------------------------------------------------------------------
# Results
# --------------------------------------------------------------------------


@admin_required
def results(request):
    config = ContestSettings.load()
    summaries = scoring.summarize_all(config)
    ranked = scoring.rank(summaries)
    divisions = []
    for value, label in DIVISION_CHOICES:
        rows = ranked.get(value, [])
        incomplete = [s for s in summaries if s.essay.division == value and not s.complete]
        divisions.append(
            {
                "value": value,
                "label": label,
                "rows": rows,
                "incomplete": len(incomplete),
                "finalists": sum(1 for s in rows if s.essay.is_finalist),
            }
        )
    return render(request, "portal/manage/results.html", {"divisions": divisions})


@admin_required
@require_POST
def finalist(request, pk):
    essay = get_object_or_404(Essay, pk=pk, status=Essay.STATUS_APPROVED)
    _toggle_finalist(request, essay)
    return redirect("manage_results")


@admin_required
def export(request, kind):
    stamp = timezone.localtime().strftime("%Y%m%d-%H%M")
    if kind in ("xlsx", "xlsx-identities"):
        identities = kind == "xlsx-identities"
        data = exports.build_workbook(include_identities=identities)
        content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = f"judging-{'with-identities-' if identities else ''}{stamp}.xlsx"
    elif kind in ("scores", "rankings"):
        data = exports.build_csv(kind)
        content_type = "text/csv; charset=utf-8"
        filename = f"{kind}-{stamp}.csv"
    else:
        raise Http404
    audit.log(request, "export_downloaded", detail=kind)
    response = HttpResponse(data, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


# --------------------------------------------------------------------------
# Configuration and logs
# --------------------------------------------------------------------------


@admin_required
def prompts(request, pk=None):
    instance = get_object_or_404(Prompt, pk=pk) if pk else None
    if request.method == "POST" and request.POST.get("action") == "delete" and instance:
        if instance.essays.exists():
            instance.is_active = False
            instance.save(update_fields=["is_active"])
            messages.info(
                request, _("This prompt has essays, so it was deactivated instead of deleted.")
            )
        else:
            instance.delete()
            messages.success(request, _("Prompt deleted."))
        return redirect("manage_prompts")
    initial = {} if instance else {"number": Prompt.objects.count() + 1}
    form = PromptForm(request.POST or None, instance=instance, initial=initial)
    if request.method == "POST" and form.is_valid():
        form.save()
        audit.log(request, "prompt_saved", target=str(form.instance))
        messages.success(request, _("Prompt saved."))
        return redirect("manage_prompts")
    return render(
        request,
        "portal/manage/prompts.html",
        {
            "form": form,
            "editing": instance,
            "prompts": Prompt.objects.annotate(
                essay_count=Count("essays", distinct=True),
                conflict_count=Count("conflicted_judges", distinct=True),
            ),
        },
    )


@admin_required
def contest_settings(request):
    config = ContestSettings.load()
    form = SettingsForm(request.POST or None, instance=config)
    if request.method == "POST" and form.is_valid():
        form.save()
        audit.log(request, "settings_changed", detail=", ".join(form.changed_data))
        messages.success(request, _("Settings saved."))
        return redirect("manage_settings")
    return render(
        request,
        "portal/manage/settings.html",
        {
            "form": form,
            "time_zone": settings.TIME_ZONE,
            "site_url": settings.SITE_URL,
            "logistics": contest.logistics(),
            "website": contest.WEBSITE,
        },
    )


@admin_required
def logs(request):
    tab = request.GET.get("tab", "audit")
    if tab == "email":
        page = paginate(request, EmailLog.objects.all(), 100)
    else:
        tab = "audit"
        page = paginate(request, AuditLog.objects.select_related("actor"), 100)
    return render(request, "portal/manage/logs.html", {"tab": tab, "page": page})
