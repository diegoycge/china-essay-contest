from decimal import Decimal

from django import template
from django.utils.html import format_html
from django.utils.translation import get_language
from django.utils.translation import gettext as _

from ..models import Assignment, Essay

register = template.Library()


@register.filter
def score(value, places=1):
    """7 -> "7.0", 7.25 -> "7.25" (when places=2). Blank for None."""
    if value is None or value == "":
        return "—"
    return f"{Decimal(value):.{int(places)}f}"


@register.filter
def prompt_label(prompt):
    if prompt is None:
        return "—"
    zh = (get_language() or "").startswith("zh")
    title = prompt.title_zh if zh and prompt.title_zh else prompt.title
    return f"{prompt.roman}. {title}"


@register.filter
def prompt_title(prompt):
    zh = (get_language() or "").startswith("zh")
    return prompt.title_zh if zh and prompt.title_zh else prompt.title


@register.filter
def prompt_text(prompt):
    zh = (get_language() or "").startswith("zh")
    return prompt.text_zh if zh and prompt.text_zh else prompt.text


ESSAY_TONES = {
    Essay.STATUS_FAILED: "danger",
    Essay.STATUS_REVIEW: "warn",
    Essay.STATUS_APPROVED: "ok",
    Essay.STATUS_DISQUALIFIED: "danger",
    Essay.STATUS_WITHDRAWN: "muted",
}
ASSIGNMENT_TONES = {
    Assignment.STATUS_ASSIGNED: "muted",
    Assignment.STATUS_DRAFT: "info",
    Assignment.STATUS_SUBMITTED: "ok",
    Assignment.STATUS_RECUSED: "warn",
    Assignment.STATUS_REMOVED: "muted",
}


@register.simple_tag
def essay_badge(essay):
    return format_html(
        '<span class="badge badge-{}">{}</span>',
        ESSAY_TONES.get(essay.status, "muted"),
        essay.get_status_display(),
    )


@register.simple_tag
def assignment_badge(assignment):
    return format_html(
        '<span class="badge badge-{}">{}</span>',
        ASSIGNMENT_TONES.get(assignment.status, "muted"),
        assignment.get_status_display(),
    )


@register.filter
def flag_title(flag):
    """Human-readable headline for an item on the reviewer's checklist."""
    kind = flag.get("kind")
    count = flag.get("count", 0)
    term = flag.get("term", "")
    done = {
        "redacted_name": _("Author’s full name: %(n)s box(es)"),
        "redacted_meta_name": _("Name from the file’s properties: %(n)s box(es)"),
        "redacted_school": _("School name: %(n)s box(es)"),
        "redacted_email": _("Email addresses: %(n)s box(es)"),
        "redacted_phone": _("Phone numbers: %(n)s box(es)"),
        "redacted_label": _("Labelled identity lines (“Name: …”): %(n)s box(es)"),
        "redacted_header": _("Repeating page header or footer: %(n)s box(es)"),
        "redacted_term": _("Words you asked to redact everywhere: %(n)s box(es)"),
        "redacted_manual": _("Boxes you drew: %(n)s"),
    }
    if kind in done:
        return done[kind] % {"n": count}
    if kind == "pages_dropped":
        return _("Pages left out (title page): %(pages)s") % {"pages": ", ".join(flag["items"])}
    if kind == "no_author_on_record":
        return _(
            "No author name on record, so the name could only be found by pattern. "
            "Import the author spreadsheet or look over every page closely."
        )
    if kind == "author_name_unusable":
        return _(
            "The author name on record is too long to match automatically. "
            "Shorten it to the person’s actual name, or redact by hand."
        )
    if kind == "no_text_layer":
        return _(
            "This PDF has little or no readable text (it may be a scan). Nothing could be "
            "found automatically: draw boxes over anything identifying yourself."
        )
    if kind == "duplicate_filename":
        return _(
            "Another upload has the same file name. Author records are matched by file name, "
            "so check by hand that the author shown here is really this essay’s author."
        )
    if kind == "name_part_present":
        return _("“%(term)s” (part of the author’s name) appears %(n)s time(s) — outlined") % {
            "term": term,
            "n": count,
        }
    if kind == "school_part_present":
        return _("“%(term)s” (from the school name) appears %(n)s time(s) — outlined") % {
            "term": term,
            "n": count,
        }
    if kind == "self_reference":
        return _("Possible self-identifying statement: %(n)s — outlined") % {"n": count}
    if kind == "header_suggested":
        return _("Repeating page header or footer without the author’s name: %(n)s — outlined") % {
            "n": count
        }
    if kind == "undergraduate_in_hs_category":
        return _(
            "The author is recorded as an undergraduate but answered a high school prompt "
            "(I–III). The rules limit undergraduates to Prompts IV–VI."
        )
    if kind == "over_word_limit":
        return _(
            "About %(n)s words on the pages; the limit is %(limit)s. The count includes "
            "footnotes, references and headers, so check before acting on it."
        ) % {"n": flag.get("count"), "limit": flag.get("limit")}
    if kind == "acknowledgements":
        return _("Acknowledgements section — may name teachers or family")
    return kind


@register.filter
def flag_tone(flag):
    kind = flag.get("kind", "")
    if kind.startswith("redacted_") or kind == "pages_dropped":
        return "done"
    return "check"


@register.filter
def failure(code):
    from ..labels import failure_text

    return failure_text(code)


@register.filter
def get_item(mapping, key):
    return mapping.get(key)
