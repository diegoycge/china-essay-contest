"""Wording for codes produced by the PDF and release machinery."""

from django.conf import settings
from django.utils.translation import gettext as _


def failure_text(code):
    """Why a submitted file could not be processed."""
    messages = {
        "password": _("The PDF is password-protected."),
        "too_many_pages": _("The PDF has more than %(n)s pages.") % {"n": settings.MAX_ESSAY_PAGES},
        "too_much_text": _("The PDF contains far more text than an essay."),
        "too_complex": _("The PDF took too long or too much memory to process."),
    }
    return messages.get(code) or _("The file is not a readable PDF.")


def problem_text(codes):
    """Why an essay cannot be released, as one sentence fragment per problem."""
    labels = {
        "no_pages": _("there are no pages left to release"),
        "duplicate_filename": _(
            "another upload has the same file name, so the author on record may be wrong "
            "(open the essay, check the author details and save them)"
        ),
        "name": _("the author’s full name is still on the pages"),
        "email": _("the author’s email address is still on the pages"),
        "any_email": _("an email address is still on the pages"),
        "school": _("the author’s school is still on the pages"),
        "no_text_layer": _(
            "this PDF has little or no readable text (it may be a scan), so nothing could be "
            "checked automatically"
        ),
    }
    return "; ".join(str(labels.get(code, code)) for code in codes)
