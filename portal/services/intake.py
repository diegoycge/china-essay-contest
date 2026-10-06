"""Bringing essays and their author records into the portal."""

import csv
import hashlib
import io
import os
import unicodedata

from django.conf import settings
from django.core.files.base import ContentFile

from ..contest import from_roman
from ..models import (
    DIVISION_HS,
    DIVISION_UG,
    Assignment,
    ContestSettings,
    Essay,
    IntakeRecord,
    Prompt,
)
from . import anonymize as anon
from . import pdf, redaction
from .text import count_words

HEADER_ALIASES = {
    "filename": {"filename", "file", "file name", "file_name", "essay file", "文件名", "文件"},
    "author_name": {"name", "author", "author name", "author_name", "full name", "student", "student name", "姓名", "作者"},
    "author_email": {"email", "e-mail", "author email", "author_email", "email address", "邮箱", "电子邮件"},
    "author_school": {"school", "institution", "university", "college", "high school", "affiliation", "author_school", "学校", "院校"},
    "division": {"division", "category", "level", "组别"},
    "prompt_ref": {"prompt", "topic", "question", "essay question", "prompt number", "题目", "题号"},
}  # fmt: skip

DIVISION_WORDS = {
    DIVISION_HS: {"hs", "high school", "highschool", "high", "secondary", "高中", "高中组", "中学"},
    DIVISION_UG: {"ug", "undergraduate", "undergrad", "college", "university", "本科", "本科组", "大学"},
}  # fmt: skip


class IntakeError(Exception):
    pass


def filename_key(name):
    name = os.path.basename(name.replace("\\", "/"))
    return unicodedata.normalize("NFC", name).strip().lower()


def parse_division(value):
    value = (value or "").strip().lower()
    for division, words in DIVISION_WORDS.items():
        if value in words:
            return division
    return ""


def resolve_prompt(ref):
    ref = (ref or "").strip()
    if not ref:
        return None
    # The contest numbers its prompts I–VI; accept "IV", "Prompt IV", "4".
    bare = ref.lower().replace("prompt", "").strip(" .:#")
    numeral = from_roman(bare)
    if numeral:
        prompt = Prompt.objects.filter(number=numeral).first()
        if prompt:
            return prompt
    digits = "".join(ch for ch in ref if ch.isdigit())
    if digits and (ref.isdigit() or len(ref) <= 12):
        prompt = Prompt.objects.filter(number=int(digits)).first()
        if prompt:
            return prompt
    return (
        Prompt.objects.filter(title__iexact=ref).first()
        or Prompt.objects.filter(title_zh=ref).first()
    )


# --------------------------------------------------------------------------
# Files
# --------------------------------------------------------------------------

GENERIC_AUTHORS = {
    "", "user", "admin", "administrator", "owner", "author", "microsoft office user",
    "windows user", "office user", "apple", "unknown", "student", "word", "(anonymous)",
    "anonymous", "(unspecified)",
}  # fmt: skip


def clean_meta_authors(names):
    """Names from a file's properties that could plausibly be the author's."""
    seen, cleaned = set(), []
    for name in names:
        name = " ".join((name or "").split())
        if name.lower() in GENERIC_AUTHORS or name.lower() in seen:
            continue
        if not anon.name_is_usable(name):
            continue
        seen.add(name.lower())
        cleaned.append(name)
    return cleaned


def recompute(essay, layout=None):
    """Refresh everything derived from the redactions and dropped pages."""
    layout = layout or pdf.load_layout(essay.work_dir)
    dropped = set(essay.dropped_pages)
    pages = redaction.released_pages(layout, essay.redactions, dropped)
    essay.released_text = "\f".join(pages)
    essay.word_count = count_words(essay.released_text)
    sticky = [f for f in essay.flags if f.get("kind") == "duplicate_filename"]
    essay.flags = redaction.summarize(
        essay.redactions,
        dropped,
        essay.released_text,
        author_name=essay.author_name,
        sticky=sticky,
    )
    essay.flags += contest_rule_flags(essay)


OVER_LIMIT_MARGIN = 1.25


def contest_rule_flags(essay):
    """Things the contest rules say the committee should look at."""
    flags = []
    category = essay.prompt.category if essay.prompt_id else ""
    if essay.author_level == DIVISION_UG and category == DIVISION_HS:
        flags.append({"kind": "undergraduate_in_hs_category"})
    limit = ContestSettings.load().word_limit
    # The count takes in footnotes, references and running heads, so only a
    # clear excess is worth the committee's attention.
    if limit and essay.word_count > limit * OVER_LIMIT_MARGIN:
        flags.append({"kind": "over_word_limit", "count": essay.word_count, "limit": limit})
    return flags


def run_auto_redaction(essay, reset=False):
    """(Re)run the automatic pass over the stored layout.

    With reset=False the reviewer's own boxes and on/off choices are kept and
    only the automatic findings are refreshed (after the author's details
    change, say). With reset=True everything starts again from scratch.
    """
    layout = pdf.load_layout(essay.work_dir)
    if reset:
        essay.dropped_pages = redaction.detect_title_page(layout)
    fresh = redaction.auto_redactions(
        layout,
        author_name=essay.author_name,
        author_school=essay.author_school,
        meta_authors=essay.meta_authors,
        dropped=essay.dropped_pages,
    )
    essay.redactions = fresh if reset else redaction.merge(essay.redactions, fresh)
    recompute(essay, layout)


def release_problems(essay):
    """Reasons this essay must not go to judges yet, as codes.

    "duplicate_filename" and "no_pages" are absolute; the rest can be
    overridden by the reviewer when they are false alarms.
    """
    problems = []
    if essay.page_count - len(set(essay.dropped_pages)) < 1 or not essay.work_dir:
        problems.append("no_pages")
    if any(f.get("kind") == "duplicate_filename" for f in essay.flags):
        problems.append("duplicate_filename")
    problems.extend(
        anon.hard_leaks(
            essay.released_text, essay.author_name, essay.author_email, essay.author_school
        )
    )
    if count_words(essay.released_text) < 50:
        problems.append("no_text_layer")
    return problems


HARD_PROBLEMS = ("no_pages", "duplicate_filename")


def write_release(essay):
    """Render the pages judges will see, replacing any earlier release."""
    previous = essay.release_dir
    essay.release_dir, essay.released_pages = pdf.render_release(
        essay.work_dir, essay.page_count, essay.redactions, set(essay.dropped_pages)
    )
    return previous


def delete_files(essay):
    if essay.original_file:
        essay.original_file.delete(save=False)
    pdf.remove_dir("work", essay.work_dir)
    pdf.remove_dir("released", essay.release_dir)


def _flag_duplicate_name(essay):
    if not any(f.get("kind") == "duplicate_filename" for f in essay.flags):
        essay.flags = [{"kind": "duplicate_filename"}] + list(essay.flags)


def create_essay_from_upload(upload, *, division, prompt, user):
    """Store one uploaded PDF. Returns (essay, outcome).

    outcome is "created", "created_unmatched" (stored, but another upload has
    the same file name so no author record was attached), "failed" (stored,
    but the file could not be processed) or "duplicate" (an identical file is
    already in the portal).
    """
    name = os.path.basename(upload.name.replace("\\", "/"))
    if os.path.splitext(name)[1].lower() != ".pdf":
        raise IntakeError("unsupported")
    if upload.size > settings.MAX_ESSAY_FILE_MB * 1024 * 1024:
        raise IntakeError("too_large")

    data = upload.read()
    if not pdf.looks_like_pdf(data):
        raise IntakeError("unsupported")
    digest = hashlib.sha256(data).hexdigest()
    existing = Essay.objects.filter(file_sha256=digest).first()
    if existing:
        return existing, "duplicate"

    key = filename_key(name)[:255]
    essay = Essay(
        division=division,
        prompt=prompt,
        original_filename=name[:255],
        filename_key=key,
        file_sha256=digest,
        uploaded_by=user,
    )
    # Author records are matched by file name. If two different files share a
    # name ("essay.pdf"), we cannot tell whose record is whose: attaching the
    # wrong author would redact the wrong name and let the right one through.
    namesakes = list(Essay.objects.filter(filename_key=key))
    if not namesakes:
        record = IntakeRecord.objects.filter(filename_key=key).first()
        if record:
            apply_record(essay, record)

    essay.original_file.save(name, ContentFile(data), save=False)
    try:
        try:
            essay.work_dir = pdf.render(essay.original_file.path)
            layout = pdf.load_layout(essay.work_dir)
            essay.page_count = len(layout["pages"])
            essay.meta_authors = clean_meta_authors(layout.get("authors", []))
            run_auto_redaction(essay, reset=True)
            outcome = "created_unmatched" if namesakes else "created"
        except pdf.PdfError as exc:
            essay.status = Essay.STATUS_FAILED
            essay.extraction_note = str(exc)[:300]
            outcome = "failed"
        if namesakes:
            _flag_duplicate_name(essay)
            for other in namesakes:
                _flag_duplicate_name(other)
                other.save(update_fields=["flags"])
        essay.save()
    except Exception:
        # Never leave identity-bearing files on disk without a record of them.
        delete_files(essay)
        raise
    return essay, outcome


# --------------------------------------------------------------------------
# Submission spreadsheet
# --------------------------------------------------------------------------


def apply_record(essay, record, classify=True):
    """Copy a spreadsheet row onto an essay. Returns True if identity changed."""
    before = (essay.author_name, essay.author_email, essay.author_school)
    essay.author_name = record.author_name or essay.author_name
    essay.author_email = record.author_email or essay.author_email
    essay.author_school = record.author_school or essay.author_school
    if record.division:
        essay.author_level = record.division
    if classify:
        prompt = resolve_prompt(record.prompt_ref)
        if prompt:
            essay.prompt = prompt
        # The category comes from the prompt; the student's own level only
        # decides it when the prompt is unknown or open to both.
        if essay.prompt and essay.prompt.category:
            essay.division = essay.prompt.category
        elif record.division:
            essay.division = record.division
    return before != (essay.author_name, essay.author_email, essay.author_school)


MAX_SHEET_BYTES = 10 * 1024 * 1024
MAX_SHEET_ROWS = 20000


def _read_rows(upload):
    name = upload.name.lower()
    if upload.size > MAX_SHEET_BYTES:
        raise IntakeError("sheet_too_large")
    data = upload.read()
    if name.endswith(".xlsx"):
        from openpyxl import load_workbook

        try:
            sheet = load_workbook(io.BytesIO(data), read_only=True, data_only=True).active
            rows = []
            for row in sheet.iter_rows(values_only=True):
                rows.append(["" if cell is None else str(cell).strip() for cell in row])
                if len(rows) > MAX_SHEET_ROWS:
                    raise IntakeError("sheet_too_large")
        except IntakeError:
            raise
        except Exception as exc:  # openpyxl raises many different errors on bad files
            raise IntakeError("sheet_unreadable") from exc
    elif name.endswith(".csv"):
        for encoding in ("utf-8-sig", "gb18030", "latin-1"):
            try:
                text = data.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        try:
            rows = [[cell.strip() for cell in row] for row in csv.reader(io.StringIO(text))]
        except csv.Error as exc:
            raise IntakeError("sheet_unreadable") from exc
        if len(rows) > MAX_SHEET_ROWS:
            raise IntakeError("sheet_too_large")
    else:
        raise IntakeError("sheet_unsupported")
    rows = [row for row in rows if any(row)]
    if len(rows) < 2:
        raise IntakeError("empty")
    return rows[0], rows[1:]


def import_metadata(upload):
    """Load author records and attach them to essays already uploaded.

    Returns a dict of counts. Essays that are still awaiting review and have
    not been hand-edited are re-redacted with the new information.
    """
    header, rows = _read_rows(upload)
    columns = {}
    for index, title in enumerate(header):
        title = title.strip().lower()
        for field, aliases in HEADER_ALIASES.items():
            if title in aliases and field not in columns:
                columns[field] = index
    if "filename" not in columns:
        raise IntakeError("no_filename_column")

    def cell(row, field):
        index = columns.get(field)
        return row[index].strip() if index is not None and index < len(row) else ""

    stats = {
        "rows": 0,
        "matched": 0,
        "reprocessed": 0,
        "skipped": 0,
        "pulled_back": 0,
        "ambiguous": [],
    }
    parsed, ambiguous = {}, {}
    for row in rows:
        filename = cell(row, "filename")
        if not filename:
            stats["skipped"] += 1
            continue
        key = filename_key(filename)[:255]
        defaults = {
            "filename": os.path.basename(filename.replace("\\", "/"))[:255],
            "author_name": cell(row, "author_name")[:200],
            "author_email": cell(row, "author_email")[:254],
            "author_school": cell(row, "author_school")[:200],
            "division": parse_division(cell(row, "division")),
            "prompt_ref": cell(row, "prompt_ref")[:200],
        }
        if key in parsed and parsed[key] != defaults:
            ambiguous[key] = defaults["filename"]
        parsed.setdefault(key, defaults)

    # The same file name listed for two different authors: use neither.
    for key in ambiguous:
        parsed.pop(key)
        IntakeRecord.objects.filter(filename_key=key).delete()

    for key, defaults in parsed.items():
        stats["rows"] += 1
        record, _created = IntakeRecord.objects.update_or_create(
            filename_key=key, defaults=defaults
        )
        essays = list(Essay.objects.filter(filename_key=key))
        if len(essays) > 1:
            # Several uploads share this name; we cannot tell which is meant.
            ambiguous[key] = defaults["filename"]
            for essay in essays:
                _flag_duplicate_name(essay)
                essay.save(update_fields=["flags"])
            continue
        for essay in essays:
            stats["matched"] += 1
            in_review = essay.status in (Essay.STATUS_REVIEW, Essay.STATUS_FAILED)
            # Do not move an essay between divisions or prompts once it has readers.
            has_readers = essay.assignments.filter(status__in=Assignment.ACTIVE_STATUSES).exists()
            changed = apply_record(essay, record, classify=not has_readers)
            if in_review and essay.work_dir:
                # Keeps the reviewer's own boxes; refreshes the automatic ones.
                run_auto_redaction(essay)
                stats["reprocessed"] += 1
            elif (
                changed
                and essay.status == Essay.STATUS_APPROVED
                and anon.hard_leaks(
                    essay.released_text, essay.author_name, essay.author_email, essay.author_school
                )
            ):
                # Released before we knew who wrote it, and the name is on the page.
                essay.status = Essay.STATUS_REVIEW
                run_auto_redaction(essay)
                stats["pulled_back"] += 1
            essay.save()
    stats["ambiguous"] = sorted(ambiguous.values())
    return stats
