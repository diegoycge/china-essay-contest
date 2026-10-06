"""Passkeys, and running the portal without an email server."""

import json
from urllib.parse import parse_qs, unquote, urlparse

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from portal.models import AccessToken, Assignment, Passkey, User
from portal.services import emails

from .authenticator import SoftAuthenticator
from .factories import make_admin, make_essay, make_judge

PASSWORD = "correct horse battery"


def post_json(client, name, data=None, **extra):
    return client.post(
        reverse(name), json.dumps(data or {}), content_type="application/json", **extra
    )


def register(client, device, **context):
    options = post_json(client, "passkey_register_options", context)
    if options.status_code != 200:
        return options
    return post_json(
        client, "passkey_register_verify", {"credential": device.create(options.json()), **context}
    )


def sign_in(client, device, **changes):
    options = post_json(client, "passkey_login_options").json()
    credential = device.get(options, **changes)
    return post_json(client, "passkey_login_verify", {"credential": credential})


class InvitationTests(TestCase):
    def setUp(self):
        self.judge = User.objects.create_user("new@example.test", full_name="New Judge")
        self.invite = emails.issue_invite(self.judge)
        self.token = self.invite.link.rstrip("/").rsplit("/", 1)[-1]
        self.device = SoftAuthenticator()

    def test_a_judge_joins_and_signs_in_with_nothing_but_a_passkey(self):
        page = self.client.get(reverse("accept_invite", args=[self.token]))
        self.assertContains(page, "Create a passkey")
        self.assertContains(page, 'data-purpose="invite"')

        done = register(self.client, self.device, token=self.token, purpose="invite")
        self.assertEqual(done.json(), {"ok": True, "redirect": reverse("home")})
        self.judge.refresh_from_db()
        self.assertFalse(self.judge.has_usable_password())
        self.assertTrue(self.judge.has_signed_in)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.judge.pk)
        key = Passkey.objects.get(user=self.judge)
        self.assertNotIn(b"PRIVATE", bytes(key.public_key))
        # The invitation is spent.
        self.assertIsNone(AccessToken.lookup(self.token, AccessToken.PURPOSE_INVITE))
        self.assertEqual(
            self.client.get(reverse("accept_invite", args=[self.token])).status_code, 410
        )

        fresh = Client()
        self.assertEqual(fresh.get(reverse("judge_onboarding")).status_code, 302)
        again = sign_in(fresh, self.device)
        self.assertEqual(again.json()["ok"], True)
        self.assertEqual(fresh.get(reverse("judge_onboarding")).status_code, 200)
        key.refresh_from_db()
        self.assertIsNotNone(key.last_used_at)

    def test_only_the_holder_of_a_live_link_can_create_the_first_passkey(self):
        self.assertEqual(post_json(self.client, "passkey_register_options").status_code, 403)
        for context in (
            {"token": "wrong", "purpose": "invite"},
            {"token": self.token, "purpose": "reset"},
            {"token": self.token, "purpose": "anything"},
            {"token": ["x"], "purpose": "invite"},
        ):
            self.assertEqual(
                register(self.client, self.device, **context).status_code, 403, context
            )
        self.assertEqual(
            self.client.post(
                reverse("passkey_register_options"), "not json", content_type="application/json"
            ).status_code,
            403,
        )
        self.assertFalse(Passkey.objects.exists())

    def test_a_password_still_works_for_those_who_prefer_it(self):
        path = reverse("accept_invite", args=[self.token])
        self.client.post(path, {"password1": PASSWORD, "password2": PASSWORD})
        self.judge.refresh_from_db()
        self.assertTrue(self.judge.check_password(PASSWORD))
        # ...and they can add a passkey later from their account page.
        self.assertEqual(register(self.client, self.device).json()["redirect"], reverse("account"))
        self.assertContains(self.client.get(reverse("account")), "Remove")


class SignInSafetyTests(TestCase):
    def setUp(self):
        self.judge = make_judge(email="j@example.test")
        self.device = SoftAuthenticator()
        self.client.force_login(self.judge)
        self.assertEqual(register(self.client, self.device).status_code, 200)
        self.client.logout()

    def test_an_answer_made_for_another_site_is_refused(self):
        phishing = SoftAuthenticator(origin="https://judging.example.net")
        phishing.key, phishing.credential_id = self.device.key, self.device.credential_id
        self.assertEqual(sign_in(self.client, phishing).json(), {"error": "invalid"})
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_an_answer_cannot_be_replayed(self):
        options = post_json(self.client, "passkey_login_options").json()
        credential = self.device.get(options)
        first = post_json(self.client, "passkey_login_verify", {"credential": credential})
        self.assertEqual(first.status_code, 200)
        other = Client()
        post_json(other, "passkey_login_options")
        replay = post_json(other, "passkey_login_verify", {"credential": credential})
        self.assertEqual(replay.json(), {"error": "invalid"})
        again = post_json(self.client, "passkey_login_verify", {"credential": credential})
        self.assertEqual(again.json(), {"error": "expired"})

    def test_the_device_must_verify_its_owner(self):
        self.assertEqual(
            sign_in(self.client, self.device, verified=False).json(), {"error": "invalid"}
        )

    def test_unknown_passkeys_and_closed_accounts(self):
        self.assertEqual(sign_in(self.client, SoftAuthenticator()).json(), {"error": "unknown"})
        User.objects.filter(pk=self.judge.pk).update(is_active=False)
        self.assertEqual(sign_in(self.client, self.device).json(), {"error": "unknown"})

    def test_requests_from_other_sites_are_refused(self):
        strict = Client(enforce_csrf_checks=True)
        for name in (
            "passkey_login_options",
            "passkey_login_verify",
            "passkey_register_options",
            "passkey_register_verify",
        ):
            self.assertEqual(post_json(strict, name).status_code, 403, name)

    @override_settings(LOGIN_MAX_FAILURES=1)
    def test_guessing_is_throttled_per_address(self):
        for _attempt in range(4):
            sign_in(self.client, SoftAuthenticator())
        self.assertEqual(sign_in(self.client, self.device).status_code, 429)
        elsewhere = Client(REMOTE_ADDR="203.0.113.50")
        self.assertEqual(sign_in(elsewhere, self.device).status_code, 200)

    def test_next_is_honoured_only_within_the_portal(self):
        for target, expected in (
            ("/judge/rubric/", "/judge/rubric/"),
            ("https://evil.example/", reverse("home")),
        ):
            client = Client()
            options = post_json(client, "passkey_login_options").json()
            data = {"credential": self.device.get(options), "next": target}
            self.assertEqual(
                post_json(client, "passkey_login_verify", data).json()["redirect"], expected
            )


class AccountTests(TestCase):
    def setUp(self):
        self.judge = User.objects.create_user("p@example.test", full_name="Passkey Only")
        self.client.force_login(self.judge)
        self.first = SoftAuthenticator()
        register(self.client, self.first)

    def test_last_way_in_cannot_be_removed(self):
        key = Passkey.objects.get()
        self.client.post(reverse("account"), {"action": "remove_passkey", "passkey": key.pk})
        self.assertTrue(Passkey.objects.filter(pk=key.pk).exists())
        # A second passkey (or a password) makes the first removable.
        register(self.client, SoftAuthenticator())
        self.client.post(reverse("account"), {"action": "remove_passkey", "passkey": key.pk})
        self.assertFalse(Passkey.objects.filter(pk=key.pk).exists())
        self.assertEqual(Passkey.objects.count(), 1)

    def test_same_device_twice_and_other_peoples_passkeys(self):
        options = post_json(self.client, "passkey_register_options").json()
        self.assertEqual(len(options["excludeCredentials"]), 1)
        again = post_json(
            self.client, "passkey_register_verify", {"credential": self.first.create(options)}
        )
        self.assertEqual(again.status_code, 409)
        other = make_judge("Other Judge")
        theirs = Passkey.objects.create(user=other, credential_id="abc", public_key=b"x")
        response = self.client.post(
            reverse("account"), {"action": "remove_passkey", "passkey": theirs.pk}
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            self.client.post(
                reverse("account"), {"action": "remove_passkey", "passkey": "x"}
            ).status_code,
            404,
        )

    def test_passkey_user_may_add_a_password(self):
        page = self.client.get(reverse("account"))
        self.assertContains(page, "Add a password")
        self.assertNotContains(page, "Current password")
        self.client.post(
            reverse("account"),
            {"action": "password", "pw-password1": PASSWORD, "pw-password2": PASSWORD},
        )
        self.judge.refresh_from_db()
        self.assertTrue(self.judge.check_password(PASSWORD))

    def test_lost_device(self):
        admin = make_admin()
        staff = Client()
        staff.force_login(admin)
        detail = reverse("manage_user", args=[self.judge.pk])
        self.assertContains(staff.get(detail), "1 passkey")
        staff.post(detail, {"action": "clear_passkeys"})
        self.assertFalse(Passkey.objects.exists())
        staff.post(detail, {"action": "reset"})
        page = staff.get(detail).content.decode()
        token = page.split("/password/reset/")[1].split("/")[0]
        replacement = SoftAuthenticator()
        fresh = Client()
        self.assertContains(fresh.get(reverse("reset_password", args=[token])), "Create a passkey")
        self.assertEqual(
            register(fresh, replacement, token=token, purpose="reset").status_code, 200
        )
        self.assertEqual(sign_in(Client(), replacement).status_code, 200)
        self.assertEqual(sign_in(Client(), self.first).json(), {"error": "unknown"})


class WithoutEmailTests(TestCase):
    """No SMTP: the admin sends prepared messages from their own mail app."""

    def setUp(self):
        self.admin = make_admin()
        self.client.force_login(self.admin)

    def test_invitation_opens_in_the_admins_mail_app(self):
        self.client.post(
            reverse("manage_users"),
            {
                "full_name": "Mei Tanaka",
                "email": "mei@example.test",
                "role": "judge",
                "language": "zh-hans",
            },
        )
        page = self.client.get(reverse("manage_users"))
        self.assertContains(page, "Open in my email app")
        html = page.content.decode()
        href = (
            html.split('class="btn btn-primary btn-small" href="')[1]
            .split('"')[0]
            .replace("&amp;", "&")
        )
        link = urlparse(href)
        self.assertEqual((link.scheme, unquote(link.path)), ("mailto", "mei@example.test"))
        fields = parse_qs(link.query)
        self.assertIn("/invite/", fields["body"][0])
        self.assertIn("通行密钥", fields["body"][0])  # written in the judge's language
        self.assertNotIn("bcc", fields)
        # Shown once: gone on the next visit.
        self.assertNotContains(self.client.get(reverse("manage_users")), "/invite/")

    def test_new_essay_notices_and_reminders(self):
        english, chinese = make_judge("Ann Lee"), make_judge("Li Hua", language="zh-hans")
        idle = make_judge("No Essays")
        for judge in (english, chinese):
            Assignment.objects.create(essay=make_essay(), judge=judge)
        drafts = emails.announcement_drafts(self.admin)
        self.assertEqual(
            [(d["language"], d["count"]) for d in drafts], [("English", 1), ("简体中文", 1)]
        )
        fields = parse_qs(urlparse(drafts[0]["mailto"]).query)
        self.assertEqual(fields["bcc"], [english.email])  # judges do not see one another
        self.assertTrue(drafts[0]["mailto"].startswith("mailto:admin%40example.test?"))
        self.assertNotIn(idle.email, " ".join(d["addresses"] for d in drafts))

        page = self.client.get(reverse("manage_assignments"))
        self.assertContains(page, "Write to 1 judge (English)", count=2)  # announce + remind
        self.assertContains(page, "does not send email itself")
        self.client.post(reverse("manage_assignments"), {"action": "mark_announced"})
        self.assertEqual(emails.announcement_drafts(self.admin), [])
        self.assertEqual(len(emails.reminder_drafts(self.admin)), 2)

    def test_large_panels_are_split_into_sendable_groups(self):
        for n in range(65):
            Assignment.objects.create(essay=make_essay(), judge=make_judge(f"Judge {n:02d}"))
        drafts = emails.reminder_drafts(self.admin)
        self.assertEqual([d["count"] for d in drafts], [30, 30, 5])
        self.assertLess(max(len(d["mailto"]) for d in drafts), 2000)
