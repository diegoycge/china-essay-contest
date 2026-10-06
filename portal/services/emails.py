"""Outgoing email. Every message is logged, in the recipient's language."""

import logging
import threading
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import quote, urlencode

from django.conf import settings
from django.core.mail import send_mail
from django.db import connections
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.formats import date_format
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from ..models import AccessToken, Assignment, ContestSettings, EmailLog, Essay, User

logger = logging.getLogger(__name__)


def absolute_url(name, *args):
    return settings.SITE_URL + reverse(name, args=args)


def _send(user, kind, subject, body, dedupe_key="", language=None):
    if not settings.EMAIL_CONFIGURED:
        # No SMTP: do not pretend. Callers show one-time links to the admin
        # instead, and assignments stay marked as not yet announced.
        return False
    if language:  # called from a background thread, outside the caller's override
        translation.activate(language)
    footer = _("This is an automated message from the judging portal. Please do not forward it.")
    entry = EmailLog(to=user.email, kind=kind, subject=subject[:300], dedupe_key=dedupe_key)
    try:
        send_mail(subject, f"{body}\n\n—\n{footer}", settings.DEFAULT_FROM_EMAIL, [user.email])
    except Exception as exc:  # SMTP failures must never break the page that triggered them
        logger.exception("Could not send %s email to %s", kind, user.email)
        entry.ok = False
        entry.error = str(exc)[:1000]
    entry.save()
    return entry.ok


def _deadline_text(deadline):
    return date_format(timezone.localtime(deadline), "DATETIME_FORMAT") if deadline else ""


@dataclass
class Message:
    """A message for one person or a group, ready to send by any means.

    With SMTP configured the portal sends it. Without, the administrator
    sends it from their own mail program: `mailto` opens it there, already
    addressed and written.
    """

    to: str
    subject: str
    body: str
    link: str = ""
    bcc: tuple = ()

    @property
    def mailto(self):
        fields = {"subject": self.subject, "body": self.body}
        if self.bcc:
            fields = {"bcc": ",".join(self.bcc), **fields}
        return f"mailto:{quote(self.to)}?{urlencode(fields, quote_via=quote)}"

    def for_session(self, kind):
        """What the "here is the link" notice needs after a redirect."""
        return {
            "kind": kind,
            "email": self.to,
            "link": self.link,
            "mailto": self.mailto,
            "message": f"{self.subject}\n\n{self.body}",
        }


def issue_invite(user, created_by=None):
    """Create a fresh invitation link and the message that carries it.

    The message is emailed if SMTP is configured; either way it is returned
    so the administrator can send or re-send it themselves.
    """
    config = ContestSettings.load()
    _row, raw = AccessToken.issue(
        user,
        AccessToken.PURPOSE_INVITE,
        timedelta(days=config.invite_valid_days),
        created_by=created_by,
    )
    link = absolute_url("accept_invite", raw)
    with translation.override(user.language):
        role = _("an administrator") if user.is_admin else _("a judge")
        subject = _("Invitation to the %(contest)s judging portal") % {
            "contest": config.contest_name
        }
        body = _(
            "Dear %(name)s,\n\n"
            "You have been invited to join the judging portal of the %(contest)s as %(role)s.\n\n"
            "Open this link to set up your sign-in. You can use a passkey (your fingerprint, "
            "face or device PIN) or choose a password:\n%(link)s\n\n"
            "The link works once and expires in %(days)s days. Please do not forward it."
        ) % {
            "name": user.full_name,
            "contest": config.contest_name,
            "role": role,
            "link": link,
            "days": config.invite_valid_days,
        }
        _send(user, "invite", subject, body)
    return Message(to=user.email, subject=subject, body=body, link=link)


def _in_background(function, *args, **kwargs):
    if not settings.EMAIL_IN_BACKGROUND:
        function(*args, **kwargs)
        return

    def run():
        try:
            function(*args, **kwargs)
        finally:
            connections.close_all()

    threading.Thread(target=run, daemon=True).start()


def issue_password_reset(user, created_by=None, self_service=False):
    """Create a reset link, email it, and return it.

    self_service is the "forgot password" page: it must not cancel a link an
    administrator has already issued, and it must not make the page slower
    for real accounts than for unknown addresses.
    """
    _row, raw = AccessToken.issue(
        user,
        AccessToken.PURPOSE_RESET,
        timedelta(hours=24),
        created_by=created_by,
        revoke_earlier=not self_service,
    )
    link = absolute_url("reset_password", raw)
    with translation.override(user.language):
        subject = _("Set up your judging portal sign-in again")
        body = _(
            "Dear %(name)s,\n\n"
            "Use this link to create a new passkey or choose a new password:\n%(link)s\n\n"
            "The link works once and expires in 24 hours. If you did not ask for it, "
            "you can ignore this message."
        ) % {"name": user.full_name, "link": link}
        if self_service:
            _in_background(_send, user, "reset", subject, body, language=user.language)
        else:
            _send(user, "reset", subject, body)
    return Message(to=user.email, subject=subject, body=body, link=link)


def unannounced_assignments():
    """Assignments a judge can act on but has not been emailed about."""
    return Assignment.objects.filter(
        notified_at__isnull=True,
        status__in=Assignment.PENDING_STATUSES,
        essay__status=Essay.STATUS_APPROVED,
        judge__is_active=True,
    ).select_related("judge", "essay")


def notify_new_assignments(assignments):
    """One email per judge covering all assignments not yet announced."""
    config = ContestSettings.load()
    by_judge = {}
    for assignment in assignments:
        # Never announce an essay the judge cannot open yet, or to a judge
        # whose account is switched off.
        if (
            assignment.notified_at is None
            and assignment.is_pending
            and assignment.essay.is_judgeable
            and assignment.judge.is_active
        ):
            by_judge.setdefault(assignment.judge, []).append(assignment)
    sent = 0
    for judge, rows in by_judge.items():
        rescore = all(a.round == Assignment.ROUND_RESCORE for a in rows)
        deadline = config.deadline_for(
            Assignment.ROUND_RESCORE if rescore else Assignment.ROUND_INITIAL
        )
        with translation.override(judge.language):
            count = len(rows)
            subject = ngettext(
                "%(count)s new essay to judge", "%(count)s new essays to judge", count
            ) % {"count": count}
            body = ngettext(
                "Dear %(name)s,\n\n%(count)s essay has been assigned to you for the %(contest)s.",
                "Dear %(name)s,\n\n%(count)s essays have been assigned to you for the %(contest)s.",
                count,
            ) % {"name": judge.full_name, "count": count, "contest": config.contest_name}
            if deadline:
                body += "\n\n" + _("Please submit your scores by %(deadline)s.") % {
                    "deadline": _deadline_text(deadline)
                }
            body += "\n\n" + _("Sign in to begin:\n%(link)s") % {"link": absolute_url("home")}
            ok = _send(judge, "assignment", subject, body)
        if ok:
            sent += 1
            Assignment.objects.filter(pk__in=[a.pk for a in rows]).update(
                notified_at=timezone.now()
            )
    return sent


def notify_admins_of_referral(referral):
    config = ContestSettings.load()
    essay = referral.assignment.essay
    for admin in User.objects.filter(role=User.ROLE_ADMIN, is_active=True):
        with translation.override(admin.language):
            subject = _("Essay %(code)s referred to the committee chair") % {"code": essay.code}
            body = _(
                "A judge has referred essay %(code)s (%(kind)s) in the %(contest)s.\n\n"
                "Review it here:\n%(link)s"
            ) % {
                "code": essay.code,
                "kind": referral.get_kind_display(),
                "contest": config.contest_name,
                "link": absolute_url("manage_referrals"),
            }
            _send(admin, "referral", subject, body)


def pending_by_judge():
    """{judge: {round: count}} for essays still waiting on a score."""
    pending = {}
    rows = Assignment.objects.filter(
        status__in=Assignment.PENDING_STATUSES,
        essay__status=Essay.STATUS_APPROVED,
        judge__is_active=True,
    ).select_related("judge")
    for assignment in rows:
        rounds = pending.setdefault(assignment.judge, {})
        rounds[assignment.round] = rounds.get(assignment.round, 0) + 1
    return pending


def _send_reminder(judge, count, deadline, overdue, dedupe_key):
    with translation.override(judge.language):
        if overdue:
            subject = _("Overdue: %(count)s essay(s) still to score") % {"count": count}
            lead = _(
                "The judging deadline (%(deadline)s) has passed and %(count)s of your assigned "
                "essay(s) have not been submitted."
            )
        else:
            subject = _("Reminder: %(count)s essay(s) to score by %(deadline)s") % {
                "count": count,
                "deadline": _deadline_text(deadline),
            }
            lead = _("You have %(count)s essay(s) still to score. The deadline is %(deadline)s.")
        body = (
            _("Dear %(name)s,") % {"name": judge.full_name}
            + "\n\n"
            + lead % {"count": count, "deadline": _deadline_text(deadline)}
            + "\n\n"
            + _("Sign in to continue:\n%(link)s") % {"link": absolute_url("home")}
        )
        return _send(judge, "reminder", subject, body, dedupe_key=dedupe_key)


def send_due_reminders(now=None):
    """Send each scheduled reminder once. Safe to call as often as you like."""
    if not settings.EMAIL_CONFIGURED:
        return 0
    now = now or timezone.now()
    config = ContestSettings.load()
    sent = 0
    for judge, rounds in pending_by_judge().items():
        for round_, count in rounds.items():
            deadline = config.deadline_for(round_)
            if not deadline:
                continue
            stamp = deadline.strftime("%Y%m%d%H%M")
            if now >= deadline:
                # One overdue notice, within the first week after the deadline.
                if now > deadline + timedelta(days=7):
                    continue
                key, overdue = f"overdue:{round_}:{stamp}:{judge.pk}", True
            else:
                due = [d for d in config.reminder_day_list() if now >= deadline - timedelta(days=d)]
                if not due:
                    continue
                key, overdue = f"reminder:{round_}:{stamp}:{min(due)}:{judge.pk}", False
            if EmailLog.objects.filter(dedupe_key=key, ok=True).exists():
                continue
            if _send_reminder(judge, count, deadline, overdue, key):
                sent += 1
    return sent


def send_manual_reminders():
    """Remind every judge with outstanding essays right now (admin button)."""
    config = ContestSettings.load()
    now = timezone.now()
    sent = 0
    for judge, rounds in pending_by_judge().items():
        count = sum(rounds.values())
        round_ = (
            Assignment.ROUND_INITIAL
            if Assignment.ROUND_INITIAL in rounds
            else Assignment.ROUND_RESCORE
        )
        deadline = config.deadline_for(round_)
        if deadline:
            ok = _send_reminder(judge, count, deadline, now >= deadline, "")
        else:
            with translation.override(judge.language):
                subject = _("Reminder: %(count)s essay(s) still to score") % {"count": count}
                body = (
                    _("Dear %(name)s,") % {"name": judge.full_name}
                    + "\n\n"
                    + _("You have %(count)s essay(s) still to score.") % {"count": count}
                    + "\n\n"
                    + _("Sign in to continue:\n%(link)s") % {"link": absolute_url("home")}
                )
                ok = _send(judge, "reminder", subject, body)
        sent += 1 if ok else 0
    return sent


# --------------------------------------------------------------------------
# Without SMTP: messages the administrator sends from their own mail program
# --------------------------------------------------------------------------

GROUP_SIZE = 30  # keeps each mailto: link short enough for every mail program


def _group_messages(judges, sender, write):
    """One Message per language (and per GROUP_SIZE recipients), sent to the
    administrator with the judges in Bcc so they do not see each other."""
    by_language = {}
    for judge in sorted(judges, key=lambda j: j.email):
        by_language.setdefault(judge.language, []).append(judge.email)
    languages = dict(settings.LANGUAGES)
    drafts = []
    for language, addresses in sorted(by_language.items()):
        with translation.override(language):
            subject, body = write()
        for start in range(0, len(addresses), GROUP_SIZE):
            chunk = tuple(addresses[start : start + GROUP_SIZE])
            message = Message(to=sender.email, subject=subject, body=body, bcc=chunk)
            drafts.append(
                {
                    "language": languages.get(language, language),
                    "count": len(chunk),
                    "addresses": ", ".join(chunk),
                    "mailto": message.mailto,
                    "message": f"{subject}\n\n{body}",
                }
            )
    return drafts


def announcement_drafts(sender):
    """Messages telling judges they have new essays (not yet announced)."""
    config = ContestSettings.load()
    judges = {assignment.judge for assignment in unannounced_assignments()}

    def write():
        subject = _("New essays to judge: %(contest)s") % {"contest": config.contest_name}
        body = _("Dear judge,\n\nNew essays have been assigned to you for the %(contest)s.") % {
            "contest": config.contest_name
        }
        if config.initial_deadline:
            body += "\n\n" + _("Please submit your scores by %(deadline)s.") % {
                "deadline": _deadline_text(config.initial_deadline)
            }
        body += "\n\n" + _("Sign in to begin:\n%(link)s") % {"link": absolute_url("home")}
        return subject, body

    return _group_messages(judges, sender, write)


def reminder_drafts(sender):
    """Messages reminding every judge who still has essays to score."""
    config = ContestSettings.load()
    judges = set(pending_by_judge())

    def write():
        subject = _("Reminder: essays still to score for the %(contest)s") % {
            "contest": config.contest_name
        }
        body = _(
            "Dear judge,\n\nA reminder that you still have essays to score for the %(contest)s."
        ) % {"contest": config.contest_name}
        if config.initial_deadline:
            body += " " + _("The deadline is %(deadline)s.") % {
                "deadline": _deadline_text(config.initial_deadline)
            }
        body += "\n\n" + _("Sign in to continue:\n%(link)s") % {"link": absolute_url("home")}
        return subject, body

    return _group_messages(judges, sender, write)


def mark_announced():
    """Record that the administrator has told judges about their new essays."""
    return unannounced_assignments().update(notified_at=timezone.now())
