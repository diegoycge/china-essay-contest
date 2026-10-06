"""Builders for test files and records."""

import json
import shutil
import tempfile
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone

from portal.demo_pdf import essay_pdf, simple_pdf  # noqa: F401 (simple_pdf is re-exported)
from portal.models import Assignment, Essay, JudgeAttestation, ScoreSheet, User

LOREM = (
    "Export controls on advanced chips slow progress in the short term, but they also "
    "give Beijing a stronger incentive to subsidize domestic fabs, so the effect of the "
    "policy depends on whether the gap can be widened faster than it can be closed. "
)
BODY = [LOREM * 3, LOREM * 3, LOREM * 2]


class MediaMixin:
    """Give each test its own, throwaway MEDIA_ROOT."""

    def setUp(self):
        super().setUp()
        self.media = tempfile.mkdtemp()
        override = override_settings(MEDIA_ROOT=self.media)
        override.enable()
        self.addCleanup(override.disable)
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)


def make_pdf(paragraphs=None, **options):
    """A formatted essay PDF; see portal.demo_pdf.essay_pdf for the options."""
    return essay_pdf(paragraphs if paragraphs is not None else BODY, **options)


def state_json(essay, **changes):
    """What the review screen posts back: boxes and dropped pages."""
    state = {"redactions": essay.redactions, "dropped": essay.dropped_pages}
    state.update(changes)
    return json.dumps(state)


def upload(name, data):
    return SimpleUploadedFile(name, data)


def make_admin(email="admin@example.test", password="correct horse battery"):
    return User.objects.create_user(email, password, full_name="Ada Admin", role=User.ROLE_ADMIN)


def make_judge(
    name="Judge One", email=None, password="correct horse battery", onboarded=True, **extra
):
    email = email or name.lower().replace(" ", ".") + "@example.test"
    judge = User.objects.create_user(email, password, full_name=name, role=User.ROLE_JUDGE, **extra)
    if onboarded:
        JudgeAttestation.objects.create(user=judge, signed_name=name)
    return judge


def make_essay(status=Essay.STATUS_APPROVED, division="ug", prompt=None, **extra):
    defaults = {
        "author_name": "Wei Zhang",
        "author_email": "wei.zhang@school.example",
        "author_school": "Riverside High School",
        "original_filename": "zhang_wei_essay.pdf",
        "page_count": 3,
        "released_pages": 2,
        "release_dir": "0" * 32,
        "released_text": "\f".join(BODY[:2]),
        "word_count": 300,
    }
    defaults.update(extra)
    essay = Essay.objects.create(status=status, division=division, prompt=prompt, **defaults)
    if status == Essay.STATUS_APPROVED:
        essay.approved_at = timezone.now()
        essay.save(update_fields=["approved_at"])
    return essay


LONG_COMMENT = "The argument is distinct and consistently argued with solid primary sources. " * 4


def submit_sheet(essay, judge, scores=(7, 7, 7, 7), round_=Assignment.ROUND_INITIAL):
    assignment, _created = Assignment.objects.get_or_create(
        essay=essay, judge=judge, defaults={"round": round_}
    )
    ScoreSheet.objects.update_or_create(
        assignment=assignment,
        defaults={
            "originality": Decimal(str(scores[0])),
            "clarity": Decimal(str(scores[1])),
            "evidence": Decimal(str(scores[2])),
            "depth": Decimal(str(scores[3])),
            "originality_comment": LONG_COMMENT,
            "clarity_comment": LONG_COMMENT,
            "evidence_comment": LONG_COMMENT,
            "depth_comment": LONG_COMMENT,
            "confirmed": True,
            "signature": judge.full_name,
        },
    )
    assignment.status = Assignment.STATUS_SUBMITTED
    assignment.submitted_at = timezone.now()
    assignment.save()
    return Assignment.objects.select_related("sheet").get(pk=assignment.pk)


def sheet_post(**overrides):
    data = {
        "originality": "7.5",
        "clarity": "6.0",
        "evidence": "8.0",
        "depth": "7.0",
        "originality_comment": LONG_COMMENT,
        "clarity_comment": LONG_COMMENT,
        "evidence_comment": LONG_COMMENT,
        "depth_comment": LONG_COMMENT,
        "overall_comment": "",
        "flag_notes": "",
        "confirmed": "on",
        "signature": "Judge One",
        "action": "submit",
    }
    data.update(overrides)
    return {key: value for key, value in data.items() if value is not None}
