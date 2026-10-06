"""Regression tests for the hardening pass."""

import re
import time
from pathlib import Path

from django.core import mail
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

import portal
from portal.forms import NewPasswordForm
from portal.models import AccessToken, Assignment, EmailLog, LoginAttempt
from portal.services import anonymize as anon
from portal.services import audit, emails, intake, redaction

from .factories import (
    LOREM,
    MediaMixin,
    make_admin,
    make_essay,
    make_judge,
    make_pdf,
    sheet_post,
    state_json,
    upload,
)

PASSWORD = "correct horse battery"


class HeaderTests(TestCase):
    def test_every_response_carries_the_policy_headers(self):
        judge = make_judge()
        self.client.force_login(judge)
        for url in (reverse("judge_dashboard"), reverse("judge_rubric"), "/no-such-page/"):
            response = self.client.get(url)
            policy = response["Content-Security-Policy"]
            self.assertIn("script-src 'self'", policy)
            self.assertNotIn("'unsafe-inline'", policy.split("script-src")[1].split(";")[0])
            self.assertIn("frame-ancestors 'none'", policy)
            self.assertEqual(response["Cache-Control"], "no-store")
            self.assertEqual(response["X-Frame-Options"], "DENY")
            self.assertEqual(response["X-Content-Type-Options"], "nosniff")

    def test_templates_have_no_inline_scripts(self):
        # The policy above would silently break any inline handler.
        root = Path(portal.__file__).parent / "templates"
        offenders = []
        for path in root.rglob("*.html"):
            text = path.read_text(encoding="utf-8")
            if re.search(r"\son[a-z]+\s*=\s*[\"']", text) or re.search(
                r"<script(?![^>]*\bsrc=)", text
            ):
                offenders.append(path.name)
        self.assertEqual(offenders, [])


class LogTests(TestCase):
    def test_one_time_tokens_are_scrubbed_from_log_lines(self):
        import logging

        from portal.logfilter import RedactOneTimeLinks

        record = logging.LogRecord(
            "django.request",
            logging.ERROR,
            "",
            0,
            "%s: %s",
            ("Internal Server Error", "/invite/s3cr3t-Token_value/"),
            None,
        )
        RedactOneTimeLinks().filter(record)
        self.assertEqual(record.getMessage(), "Internal Server Error: /invite/<redacted>/")
        record = logging.LogRecord(
            "x", logging.WARNING, "", 0, "Gone: /password/reset/abc123/", None, None
        )
        RedactOneTimeLinks().filter(record)
        self.assertNotIn("abc123", record.getMessage())


class ThrottleTests(TestCase):
    def setUp(self):
        self.judge = make_judge(email="j@example.test")
        self.url = reverse("login")

    def _fail(self, email, ip):
        return self.client.post(self.url, {"email": email, "password": "wrong"}, REMOTE_ADDR=ip)

    @override_settings(LOGIN_MAX_FAILURES=2)
    def test_one_address_cannot_try_many_accounts(self):
        for n in range(8):
            self._fail(f"user{n}@example.test", "198.51.100.7")
        blocked = self.client.post(
            self.url, {"email": "j@example.test", "password": PASSWORD}, REMOTE_ADDR="198.51.100.7"
        )
        self.assertContains(blocked, "Too many failed attempts")
        elsewhere = self.client.post(
            self.url, {"email": "j@example.test", "password": PASSWORD}, REMOTE_ADDR="198.51.100.8"
        )
        self.assertEqual(elsewhere.status_code, 302)

    @override_settings(LOGIN_MAX_FAILURES=2)
    def test_many_addresses_cannot_grind_one_account(self):
        for n in range(10):
            self._fail("j@example.test", f"203.0.113.{n}")
        blocked = self.client.post(
            self.url, {"email": "j@example.test", "password": PASSWORD}, REMOTE_ADDR="192.0.2.1"
        )
        self.assertContains(blocked, "Too many failed attempts")
        self.assertEqual(LoginAttempt.objects.count(), 10)

    def test_forwarded_address_cannot_be_forged(self):
        request = RequestFactory().get(
            "/", HTTP_X_FORWARDED_FOR="10.9.9.9, 203.0.113.5", REMOTE_ADDR="172.18.0.2"
        )
        with override_settings(BEHIND_PROXY=True):
            self.assertEqual(audit.client_ip(request), "203.0.113.5")
        with override_settings(BEHIND_PROXY=False):
            self.assertEqual(audit.client_ip(request), "172.18.0.2")

    def test_password_may_not_be_the_users_own_name(self):
        judge = make_judge("Margaret Hamilton")
        form = NewPasswordForm(
            judge, {"password1": "margarethamilton", "password2": "margarethamilton"}
        )
        self.assertFalse(form.is_valid())


class NoSmtpTests(TestCase):
    """Without SMTP nothing is sent, logged as sent, or printed."""

    def test_links_are_handed_to_the_admin_only(self):
        admin = make_admin()
        self.client.force_login(admin)
        self.client.post(
            reverse("manage_users"),
            {
                "full_name": "New Judge",
                "email": "new@example.test",
                "role": "judge",
                "language": "en",
            },
        )
        page = self.client.get(reverse("manage_users"))
        self.assertContains(page, "/invite/")
        self.assertContains(page, "Nothing has been sent yet")
        self.assertEqual((len(mail.outbox), EmailLog.objects.count()), (0, 0))

    def test_self_service_reset_issues_no_token(self):
        judge = make_judge(email="j@example.test")
        response = self.client.post(reverse("forgot_password"), {"email": "j@example.test"})
        self.assertContains(response, "cannot send email")
        self.assertFalse(AccessToken.objects.filter(user=judge).exists())

    def test_assignments_stay_unannounced_and_reminders_idle(self):
        judge = make_judge()
        row = Assignment.objects.create(essay=make_essay(), judge=judge)
        self.assertEqual(emails.notify_new_assignments([row]), 0)
        row.refresh_from_db()
        self.assertIsNone(row.notified_at)
        self.assertEqual(emails.send_due_reminders(), 0)
        self.assertEqual(emails.send_manual_reminders(), 0)


class RobustnessTests(MediaMixin, TestCase):
    def test_hostile_text_cannot_stall_the_patterns(self):
        started = time.monotonic()
        anon.EMAIL_RE.findall("a" * 1_000_000)
        anon.EMAIL_RE.findall("a.b-" * 300_000 + "@")
        anon.phone_spans("123 " * 250_000)
        anon.SELF_REFERENCE_RE.findall("I am a " * 150_000)
        anon.is_identity_line("by" + ":" * 150_000 + " x y")
        anon.is_page_number("page" + " " * 200_000 + "x")
        self.assertLess(time.monotonic() - started, 5)

    def test_email_redaction_still_works(self):
        found = anon.EMAIL_RE.findall(
            "Write to wei.zhang+x@school.example.cn or <a@b.org>, not user@host."
        )
        self.assertEqual(found, ["wei.zhang+x@school.example.cn", "a@b.org"])

    def test_the_worker_runs_outside_the_web_process(self):
        # Parsing happens in a child process with its own limits; the parent
        # only ever reads the PNGs and the JSON it wrote.
        import subprocess
        from unittest import mock

        from portal.services import pdf

        real = subprocess.run
        with mock.patch("portal.services.pdf.subprocess.run", side_effect=real) as run:
            essay, outcome = intake.create_essay_from_upload(
                upload("e.pdf", make_pdf()), division="ug", prompt=None, user=None
            )
        self.assertEqual(outcome, "created")
        (command,), options = run.call_args
        self.assertEqual(command[1:3], ["-m", "portal.pdfworker"])
        self.assertEqual(command[-2:], ["60", "2048"])  # CPU seconds and MB it limits itself to
        self.assertNotIn("SECRET_KEY", options["env"])
        self.assertNotIn("DATABASE_URL", options["env"])
        with self.assertRaises(pdf.PdfError):
            pdf.dir_path("work", "../../etc")

    def test_bad_spreadsheets_are_reported_not_crashed(self):
        self.client.force_login(make_admin())
        for name, data in (
            ("authors.xlsx", b"not a zip"),
            ("authors.pdf", b"%PDF"),
            ("authors.csv", b"only\n"),
        ):
            response = self.client.post(
                reverse("manage_import_metadata"), {"sheet": upload(name, data)}, follow=True
            )
            self.assertEqual(response.status_code, 200, name)
            self.assertFalse(intake.IntakeRecord.objects.exists())

    def test_malformed_ids_are_not_found(self):
        self.client.force_login(make_admin())
        essay = make_essay()
        detail = reverse("manage_essay", args=[essay.pk])
        cases = [
            (reverse("manage_divergence"), {"essay": "abc"}),
            (reverse("manage_referrals"), {"referral": "1 OR 1=1", "action": "dismiss"}),
            (detail, {"action": "assign", "judge": "x"}),
            (detail, {"action": "remove_assignment", "assignment": "-1"}),
        ]
        for url, data in cases:
            self.assertEqual(self.client.post(url, data).status_code, 404, data)

    def test_no_late_write_after_removal_or_submission(self):
        judge = make_judge()
        essay = make_essay()
        row = Assignment.objects.create(essay=essay, judge=judge)
        self.client.force_login(judge)
        autosave = reverse("judge_autosave", args=[essay.code])
        self.assertEqual(self.client.post(autosave, {"originality": "5.0"}).status_code, 200)
        self.client.post(reverse("judge_sheet", args=[essay.code]), sheet_post())
        row.refresh_from_db()
        self.assertEqual(row.status, Assignment.STATUS_SUBMITTED)
        self.assertEqual(self.client.post(autosave, {"originality": "0.0"}).status_code, 409)
        self.assertEqual(
            self.client.post(
                reverse("judge_recuse", args=[essay.code]), {"reason": "late"}
            ).status_code,
            403,
        )
        row.sheet.refresh_from_db()
        self.assertEqual(str(row.sheet.originality), "7.5")


class ReviewFindingsTests(MediaMixin, TestCase):
    """One test per finding from the independent review."""

    def setUp(self):
        super().setUp()
        self.admin = make_admin()

    def _pdf(self, first_line, salt=""):
        return make_pdf([first_line, LOREM * 3 + salt, LOREM * 3], author="x")

    def _upload(self, name, data):
        return intake.create_essay_from_upload(
            upload(name, data), division="ug", prompt=None, user=None
        )

    # 1 ------------------------------------------------------------------
    def test_same_file_name_never_attaches_the_wrong_author(self):
        from portal.models import Essay

        sheet = "filename,name\nfolderA/essay.pdf,Alice Anderson\nfolderB/essay.pdf,Bob Brown\nsolo.pdf,Cara Diaz\n"
        stats = intake.import_metadata(upload("authors.csv", sheet.encode()))
        self.assertEqual(stats["ambiguous"], ["essay.pdf"])
        self.assertEqual(intake.IntakeRecord.objects.count(), 1)
        alice, outcome = self._upload("essay.pdf", self._pdf("Alice Anderson", "a"))
        self.assertEqual((outcome, alice.author_name), ("created", ""))

        # Spreadsheet lists the name once, but two different files carry it.
        intake.import_metadata(upload("authors.csv", b"filename,name\npaper.pdf,Dan Evans\n"))
        first, outcome = self._upload("paper.pdf", self._pdf("Dan Evans", "1"))
        self.assertEqual((outcome, first.author_name), ("created", "Dan Evans"))
        second, outcome = self._upload("paper.pdf", self._pdf("Erin Fox", "2"))
        self.assertEqual((outcome, second.author_name), ("created_unmatched", ""))
        first.refresh_from_db()
        for essay in (first, second):
            self.assertIn("duplicate_filename", [f["kind"] for f in essay.flags])
        # Re-importing must not paint both with one author either.
        stats = intake.import_metadata(
            upload("authors.csv", b"filename,name\npaper.pdf,Dan Evans\n")
        )
        second.refresh_from_db()
        self.assertEqual((stats["ambiguous"], second.author_name), (["paper.pdf"], ""))

        # Neither can be released until an admin has vouched for the author.
        self.client.force_login(self.admin)
        review = reverse("manage_review", args=[second.pk])
        self.client.post(
            review, {"action": "approve", "state": state_json(second), "override": "1"}
        )
        second.refresh_from_db()
        self.assertEqual(second.status, Essay.STATUS_REVIEW)
        self.client.post(
            reverse("manage_essay", args=[second.pk]),
            {"action": "save_meta", "division": "ug", "author_name": "Erin Fox"},
        )
        second.refresh_from_db()
        self.assertNotIn("Erin Fox", second.released_text)
        self.client.post(review, {"action": "approve", "state": state_json(second)})
        second.refresh_from_db()
        self.assertEqual(second.status, Essay.STATUS_APPROVED)

    # 2 ------------------------------------------------------------------
    def test_released_pages_cannot_change_without_passing_the_gate(self):
        from portal.models import Essay

        essay, _outcome = self._upload("bob.pdf", self._pdf("This was written by Bob Brown."))
        Essay.objects.filter(pk=essay.pk).update(author_name="Bob Brown")
        essay.refresh_from_db()
        intake.run_auto_redaction(essay)
        essay.save()
        self.client.force_login(self.admin)
        review = reverse("manage_review", args=[essay.pk])
        self.client.post(review, {"action": "approve", "state": state_json(essay)})
        essay.refresh_from_db()
        self.assertEqual(essay.status, Essay.STATUS_APPROVED)
        released, boxes = essay.release_dir, essay.redactions

        # Switching the name's box off on a live essay is refused outright.
        exposed = [dict(b, on=False) if b["kind"] == "name" else b for b in boxes]
        self.client.post(review, {"action": "save", "state": state_json(essay, redactions=exposed)})
        essay.refresh_from_db()
        self.assertEqual(
            (essay.status, essay.redactions, essay.release_dir), ("approved", boxes, released)
        )

        # A harmless change is accepted and judges get freshly rendered pages.
        extra = boxes + [
            {"p": 0, "x": 0.1, "y": 0.8, "w": 0.2, "h": 0.03, "kind": "manual", "on": True}
        ]
        self.client.post(review, {"action": "save", "state": state_json(essay, redactions=extra)})
        essay.refresh_from_db()
        self.assertEqual(essay.status, Essay.STATUS_APPROVED)
        self.assertNotEqual(essay.release_dir, released)
        from portal.services import pdf

        self.assertFalse(pdf.dir_path("released", released).exists())

        self.client.post(review, {"action": "rerun"})
        essay.refresh_from_db()
        self.assertEqual(essay.status, Essay.STATUS_REVIEW)

    # 4, 7 ---------------------------------------------------------------
    def test_crafted_names_cannot_stall_redaction(self):
        hostile_name = " ".join(["A"] * 39 + ["Z"])
        body = [" ".join(["a"] * 60), LOREM * 3, LOREM * 3]
        started = time.monotonic()
        essay, outcome = self._upload("h.pdf", make_pdf(body, author=hostile_name))
        self.assertEqual((outcome, essay.meta_authors), ("created", []))
        essay.author_name = hostile_name
        intake.run_auto_redaction(essay)
        intake.release_problems(essay)
        self.assertLess(time.monotonic() - started, 8)
        self.assertIn("author_name_unusable", [f["kind"] for f in essay.flags])

    def test_posted_state_is_bounded(self):
        huge = [
            {"p": 0, "x": 0.1, "y": 0.1, "w": 0.1, "h": 0.1, "kind": "manual", "on": True}
        ] * 20_000
        self.assertEqual(len(redaction.clean(huge, 1)), 5000)

    # 5 ------------------------------------------------------------------
    def test_control_characters_do_not_break_the_export(self):
        from portal.services import exports

        from .factories import submit_sheet

        sheet = submit_sheet(make_essay(), make_judge()).sheet
        sheet.overall_comment = "fine\x0bwork\x01" + "x" * 40_000
        sheet.save()
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("manage_export", args=["xlsx"])).status_code, 200)
        self.assertEqual(exports._safe("a\x0bb"), "ab")

    # 6 ------------------------------------------------------------------
    def test_two_closest_rule_does_not_depend_on_reader_order(self):
        from decimal import Decimal as D
        from itertools import permutations

        from portal.models import ContestSettings
        from portal.services import scoring

        from .factories import submit_sheet

        rule = ContestSettings.RESCORE_CLOSEST_TWO
        results = {scoring.combine(list(order), rule) for order in permutations([D(5), D(9), D(7)])}
        self.assertEqual(results, {D(7)})
        self.assertEqual(scoring.combine([D(5), D(9), D(8)], rule), D("8.5"))

        # Without a re-score the rule does not apply, even with three readers.
        config = ContestSettings.load()
        config.readers_per_essay, config.rescore_method, config.divergence_threshold = (
            3,
            rule,
            D("10"),
        )
        essay = make_essay()
        for name, value in (("A", 5), ("B", 9), ("C", 8)):
            submit_sheet(essay, make_judge(f"Judge {name}"), (value,) * 4)
        self.assertEqual(scoring.summarize(essay, config).final, D("7.33"))

    # 8, 9 ---------------------------------------------------------------
    def test_malformed_files_fail_cleanly_and_leave_nothing_behind(self):
        import os

        from portal.models import Essay

        essay, outcome = self._upload("broken.pdf", b"%PDF-1.7\n" + os.urandom(4000))
        self.assertEqual((outcome, essay.status), ("failed", Essay.STATUS_FAILED))
        with self.assertRaises(intake.IntakeError):
            self._upload("essay.txt", b"plain text is not accepted any more")
        stored = [f for _d, _s, files in os.walk(self.media) for f in files]
        self.assertEqual(len(stored), Essay.objects.count())  # one original, nothing orphaned

    # 10 -----------------------------------------------------------------
    @override_settings(EMAIL_CONFIGURED=True)
    def test_rescore_reader_is_not_overdue_on_arrival(self):
        from datetime import timedelta

        from django.utils import timezone

        from portal.models import ContestSettings

        config = ContestSettings.load()
        config.initial_deadline = timezone.now() - timedelta(days=2)
        config.save()
        judge = make_judge()
        Assignment.objects.create(essay=make_essay(), judge=judge, round=Assignment.ROUND_RESCORE)
        self.assertIsNone(config.deadline_for(Assignment.ROUND_RESCORE))
        self.assertEqual(emails.send_due_reminders(), 0)

    # 11 -----------------------------------------------------------------
    @override_settings(EMAIL_CONFIGURED=True)
    def test_only_openable_essays_are_announced(self):
        from portal.models import Essay

        hidden = Assignment.objects.create(
            essay=make_essay(status=Essay.STATUS_REVIEW), judge=make_judge("A B")
        )
        gone = Assignment.objects.create(
            essay=make_essay(), judge=make_judge("C D", is_active=False)
        )
        ready = Assignment.objects.create(essay=make_essay(), judge=make_judge("E F"))
        self.assertEqual(list(emails.unannounced_assignments()), [ready])
        self.assertEqual(emails.notify_new_assignments([hidden, gone, ready]), 1)
        hidden.refresh_from_db()
        self.assertIsNone(hidden.notified_at)

    # 12, 13 -------------------------------------------------------------
    @override_settings(EMAIL_CONFIGURED=True, LOGIN_MAX_FAILURES=1)
    def test_reset_keeps_admin_link_and_lifts_lockout(self):
        judge = make_judge(email="j@example.test")
        from datetime import timedelta

        from django.utils import timezone

        admin_link = emails.issue_password_reset(judge, created_by=self.admin).link
        # (Self-service requests are limited to one per five minutes per account.)
        AccessToken.objects.update(created_at=timezone.now() - timedelta(minutes=10))
        self.client.post(reverse("forgot_password"), {"email": "j@example.test"})
        self.assertEqual(AccessToken.objects.filter(user=judge, used_at__isnull=True).count(), 2)

        for n in range(6):
            self.client.post(
                reverse("login"),
                {"email": "j@example.test", "password": "wrong"},
                REMOTE_ADDR=f"203.0.113.{n}",
            )
        locked = self.client.post(
            reverse("login"), {"email": "j@example.test", "password": PASSWORD}
        )
        self.assertContains(locked, "Too many failed attempts")
        path = admin_link.replace("http://localhost:8000", "")
        new = "a much better passphrase"
        self.client.post(path, {"password1": new, "password2": new})
        back = self.client.post(reverse("login"), {"email": "j@example.test", "password": new})
        self.assertEqual(back.status_code, 302)

    # 14 -----------------------------------------------------------------
    def test_comments_have_a_size_limit(self):
        judge = make_judge()
        essay = make_essay()
        Assignment.objects.create(essay=essay, judge=judge)
        self.client.force_login(judge)
        response = self.client.post(
            reverse("judge_autosave", args=[essay.code]), {"overall_comment": "x" * 20_001}
        )
        self.assertEqual(response.status_code, 400)

    # 15 -----------------------------------------------------------------
    def test_late_author_import_rechecks_released_essays(self):
        from portal.models import Essay, Prompt

        prompt = Prompt.objects.create(number=1, title="Chips")
        essay, _outcome = self._upload("late.pdf", self._pdf("Gina Hale wrote this essay."))
        intake.write_release(essay)
        essay.status = Essay.STATUS_APPROVED
        essay.save()
        Assignment.objects.create(essay=essay, judge=make_judge())
        sheet = b"filename,name,division,prompt\nlate.pdf,Gina Hale,high school,1\n"
        stats = intake.import_metadata(upload("authors.csv", sheet))
        essay.refresh_from_db()
        self.assertEqual(stats["pulled_back"], 1)
        self.assertEqual(essay.status, Essay.STATUS_REVIEW)
        self.assertNotIn("Gina Hale", essay.released_text)
        # It already has a reader, so it is not moved to another division or prompt.
        self.assertEqual((essay.division, essay.prompt), ("ug", None))
        self.assertNotEqual(prompt.pk, essay.prompt_id)

    # 16 -----------------------------------------------------------------
    def test_no_prompt_means_no_judge_with_declared_conflicts(self):
        from portal.models import Prompt
        from portal.services import assignment as assigner

        prompt = Prompt.objects.create(number=1, title="Taiwan")
        conflicted = make_judge("Has Conflict")
        conflicted.attestation.conflict_prompts.add(prompt)
        free = make_judge("No Conflict")
        essay = make_essay(prompt=None)
        self.assertEqual([j.pk for j in assigner.candidates_for(essay)], [free.pk])
