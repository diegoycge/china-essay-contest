import hashlib
import secrets
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

# No 0/O or 1/I/L so codes survive being read aloud or copied by hand.
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"

DIVISION_HS = "hs"
DIVISION_UG = "ug"
DIVISION_CHOICES = [
    (DIVISION_HS, _("High school")),
    (DIVISION_UG, _("Undergraduate")),
]

CRITERIA_KEYS = ("originality", "clarity", "evidence", "depth")


def generate_essay_code():
    return "E-" + "".join(secrets.choice(CODE_ALPHABET) for _ in range(5))


def hash_token(raw):
    return hashlib.sha256(raw.encode()).hexdigest()


# --------------------------------------------------------------------------
# Accounts
# --------------------------------------------------------------------------


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra):
        if not email:
            raise ValueError("Email is required")
        user = self.model(email=self.normalize_email(email).lower(), **extra)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("role", User.ROLE_ADMIN)
        return self.create_user(email, password, **extra)


class User(AbstractBaseUser):
    ROLE_ADMIN = "admin"
    ROLE_JUDGE = "judge"
    ROLE_CHOICES = [(ROLE_ADMIN, _("Admin")), (ROLE_JUDGE, _("Judge"))]

    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=200)
    affiliation = models.CharField(max_length=200, blank=True)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default=ROLE_JUDGE)
    is_active = models.BooleanField(default=True)
    language = models.CharField(max_length=10, choices=settings.LANGUAGES, default="en")
    # Optional cap on how many essays auto-assignment may give this judge.
    max_load = models.PositiveIntegerField(null=True, blank=True)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        ordering = ["full_name", "email"]

    def __str__(self):
        return self.full_name or self.email

    @property
    def is_admin(self):
        return self.role == self.ROLE_ADMIN

    @property
    def is_judge(self):
        return self.role == self.ROLE_JUDGE

    @property
    def has_signed_in(self):
        """Whether the person has set up a way to sign in (password or passkey)."""
        return self.has_usable_password() or self.last_login is not None

    @property
    def is_onboarded(self):
        return hasattr(self, "attestation")


class AccessToken(models.Model):
    """One-time link for accepting an invitation or resetting a password.

    Only the SHA-256 of the token is stored; the raw value exists in the
    emailed link alone.
    """

    PURPOSE_INVITE = "invite"
    PURPOSE_RESET = "reset"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="access_tokens")
    purpose = models.CharField(max_length=10)
    token_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    @classmethod
    def issue(cls, user, purpose, valid_for, created_by=None, revoke_earlier=True):
        """Return (token_row, raw_token), by default invalidating earlier links.

        Self-service password resets pass revoke_earlier=False: otherwise
        anyone who knows an email address could keep cancelling the link an
        administrator just handed that person.
        """
        if revoke_earlier:
            cls.objects.filter(user=user, purpose=purpose, used_at__isnull=True).update(
                used_at=timezone.now()
            )
        raw = secrets.token_urlsafe(32)
        row = cls.objects.create(
            user=user,
            purpose=purpose,
            token_hash=hash_token(raw),
            expires_at=timezone.now() + valid_for,
            created_by=created_by,
        )
        return row, raw

    @classmethod
    def lookup(cls, raw, purpose):
        row = (
            cls.objects.select_related("user")
            .filter(token_hash=hash_token(raw), purpose=purpose)
            .first()
        )
        if row and row.used_at is None and row.expires_at > timezone.now() and row.user.is_active:
            return row
        return None


class Passkey(models.Model):
    """A WebAuthn credential: the public half of a key that lives on a
    person's phone, laptop or security key. Nothing here is secret."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="passkeys")
    credential_id = models.CharField(max_length=1400, unique=True)  # base64url
    public_key = models.BinaryField()
    sign_count = models.PositiveBigIntegerField(default=0)
    name = models.CharField(max_length=80, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at", "id"]


class LoginAttempt(models.Model):
    email = models.CharField(max_length=254, db_index=True)
    ip = models.CharField(max_length=64, blank=True)
    success = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)


# --------------------------------------------------------------------------
# Contest configuration
# --------------------------------------------------------------------------


class ContestSettings(models.Model):
    RESCORE_MEAN_ALL = "mean_all"
    RESCORE_CLOSEST_TWO = "closest_two"
    RESCORE_CHOICES = [
        (RESCORE_MEAN_ALL, _("Average of all readers")),
        (RESCORE_CLOSEST_TWO, _("Average of the two closest readers")),
    ]

    contest_name = models.CharField(
        max_length=200, default="Duke-UNC China Leadership Summit (CLS) Essay Contest 2026"
    )
    # Published limit on essay length, shown to judges and used to flag long essays.
    word_limit = models.PositiveIntegerField(default=1500)
    # Where judges are told to write with questions.
    contact_email = models.EmailField(blank=True, default="contact@dukeunccls.com")
    readers_per_essay = models.PositiveSmallIntegerField(
        default=2, validators=[MinValueValidator(1), MaxValueValidator(6)]
    )
    divergence_threshold = models.DecimalField(
        max_digits=3,
        decimal_places=1,
        default=Decimal("2.0"),
        validators=[MinValueValidator(Decimal("0.5")), MaxValueValidator(Decimal("10"))],
    )
    rescore_method = models.CharField(
        max_length=20, choices=RESCORE_CHOICES, default=RESCORE_MEAN_ALL
    )
    min_comment_words = models.PositiveSmallIntegerField(default=100)
    initial_deadline = models.DateTimeField(null=True, blank=True)
    rescore_deadline = models.DateTimeField(null=True, blank=True)
    # Comma-separated days before a deadline on which reminder emails go out.
    reminder_days = models.CharField(max_length=50, default="3,1", blank=True)
    invite_valid_days = models.PositiveSmallIntegerField(default=14)

    class Meta:
        verbose_name_plural = "contest settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj

    def deadline_for(self, round_):
        if round_ == Assignment.ROUND_RESCORE:
            if self.rescore_deadline:
                return self.rescore_deadline
            # Re-scores borrow the main deadline only while it is still ahead;
            # a reader assigned after it has passed is not instantly "overdue".
            if self.initial_deadline and self.initial_deadline > timezone.now():
                return self.initial_deadline
            return None
        return self.initial_deadline

    def reminder_day_list(self):
        days = []
        for part in self.reminder_days.split(","):
            part = part.strip()
            if part.isdigit() and int(part) > 0:
                days.append(int(part))
        return sorted(set(days), reverse=True)


class Prompt(models.Model):
    """An essay question. Judges declare conflicts against these."""

    DIVISION_BOTH = "both"
    PROMPT_DIVISION_CHOICES = [(DIVISION_BOTH, _("Both divisions"))] + DIVISION_CHOICES

    number = models.PositiveSmallIntegerField()
    division = models.CharField(
        max_length=5, choices=PROMPT_DIVISION_CHOICES, default=DIVISION_BOTH
    )
    title = models.CharField(max_length=200)
    title_zh = models.CharField(max_length=200, blank=True)
    text = models.TextField(blank=True)
    text_zh = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["number", "id"]

    def __str__(self):
        return f"{self.roman}. {self.title}"

    @property
    def roman(self):
        from .contest import roman

        return roman(self.number)

    @property
    def category(self):
        """The division this prompt belongs to, or "" if it is open to both."""
        return self.division if self.division != self.DIVISION_BOTH else ""


# --------------------------------------------------------------------------
# Judges
# --------------------------------------------------------------------------


class JudgeAttestation(models.Model):
    """The signed pre-judging statement required by the committee notes."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="attestation")
    signed_name = models.CharField(max_length=200)
    signed_at = models.DateTimeField(default=timezone.now)
    conflict_prompts = models.ManyToManyField(Prompt, blank=True, related_name="conflicted_judges")
    conflict_notes = models.TextField(blank=True)
    ip = models.CharField(max_length=64, blank=True)


# --------------------------------------------------------------------------
# Essays
# --------------------------------------------------------------------------


def essay_upload_path(instance, filename):
    # The stored name never contains the author's filename.
    return f"originals/{secrets.token_hex(16)}.pdf"


class IntakeRecord(models.Model):
    """A row from the submission spreadsheet, matched to essays by filename."""

    filename_key = models.CharField(max_length=255, unique=True)
    filename = models.CharField(max_length=255)
    author_name = models.CharField(max_length=200, blank=True)
    author_email = models.CharField(max_length=254, blank=True)
    author_school = models.CharField(max_length=200, blank=True)
    division = models.CharField(max_length=5, blank=True)
    prompt_ref = models.CharField(max_length=200, blank=True)
    imported_at = models.DateTimeField(default=timezone.now)


class Essay(models.Model):
    STATUS_FAILED = "failed"
    STATUS_REVIEW = "needs_review"
    STATUS_APPROVED = "approved"
    STATUS_DISQUALIFIED = "disqualified"
    STATUS_WITHDRAWN = "withdrawn"
    STATUS_CHOICES = [
        (STATUS_FAILED, _("File could not be processed")),
        (STATUS_REVIEW, _("Needs anonymization review")),
        (STATUS_APPROVED, _("Released to judges")),
        (STATUS_DISQUALIFIED, _("Disqualified")),
        (STATUS_WITHDRAWN, _("Withdrawn")),
    ]

    code = models.CharField(max_length=12, unique=True, editable=False)
    division = models.CharField(max_length=5, choices=DIVISION_CHOICES)
    prompt = models.ForeignKey(
        Prompt, null=True, blank=True, on_delete=models.SET_NULL, related_name="essays"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_REVIEW)

    # Identity — visible to admins only, never rendered in judge views.
    author_name = models.CharField(max_length=200, blank=True)
    author_email = models.CharField(max_length=254, blank=True)
    author_school = models.CharField(max_length=200, blank=True)
    # Whether the author is a high school or undergraduate student. This can
    # differ from `division`: a high school student who answers an
    # undergraduate prompt is judged in the undergraduate category.
    author_level = models.CharField(max_length=5, choices=DIVISION_CHOICES, blank=True)
    original_file = models.FileField(upload_to=essay_upload_path, max_length=200, blank=True)
    original_filename = models.CharField(max_length=255, blank=True)
    filename_key = models.CharField(max_length=255, blank=True, db_index=True)
    file_sha256 = models.CharField(max_length=64, blank=True, db_index=True)
    # Author names found in the file's document properties (used for redaction).
    meta_authors = models.JSONField(default=list, blank=True)

    # The submitted PDF, rendered. work_dir holds the unredacted page images
    # and the position of every word (admins only).
    page_count = models.PositiveSmallIntegerField(default=0)
    work_dir = models.CharField(max_length=32, blank=True)
    # Rectangles on pages, as fractions of the page: {p, x, y, w, h, kind, on}.
    redactions = models.JSONField(default=list, blank=True)
    dropped_pages = models.JSONField(default=list, blank=True)

    # What judges read: release_dir holds page images with the applied
    # redactions burned in, written when the essay is released.
    release_dir = models.CharField(max_length=32, blank=True)
    released_pages = models.PositiveSmallIntegerField(default=0)
    # The same pages as plain text (covered words removed), for copying a
    # reference or searching. Pages are separated by form feeds.
    released_text = models.TextField(blank=True)

    flags = models.JSONField(default=list, blank=True)
    extraction_note = models.CharField(max_length=300, blank=True)
    word_count = models.PositiveIntegerField(default=0)

    admin_notes = models.TextField(blank=True)
    is_finalist = models.BooleanField(default=False)
    finalist_confirmed_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    finalist_confirmed_at = models.DateTimeField(null=True, blank=True)

    uploaded_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    uploaded_at = models.DateTimeField(default=timezone.now)
    approved_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-uploaded_at", "-id"]

    def __str__(self):
        return self.code

    def save(self, *args, **kwargs):
        if not self.code:
            code = generate_essay_code()
            while Essay.objects.filter(code=code).exists():
                code = generate_essay_code()
            self.code = code
        # Contest rule: an essay is judged in the category of the prompt it
        # answers, whoever wrote it.
        if self.prompt_id and kwargs.get("update_fields") is None and self.prompt.category:
            self.division = self.prompt.category
        super().save(*args, **kwargs)

    @property
    def is_judgeable(self):
        return self.status == self.STATUS_APPROVED


class Assignment(models.Model):
    ROUND_INITIAL = "initial"
    ROUND_RESCORE = "rescore"
    ROUND_CHOICES = [(ROUND_INITIAL, _("Initial")), (ROUND_RESCORE, _("Re-score"))]

    STATUS_ASSIGNED = "assigned"
    STATUS_DRAFT = "draft"
    STATUS_SUBMITTED = "submitted"
    STATUS_RECUSED = "recused"
    STATUS_REMOVED = "removed"
    STATUS_CHOICES = [
        (STATUS_ASSIGNED, _("Not started")),
        (STATUS_DRAFT, _("In progress")),
        (STATUS_SUBMITTED, _("Submitted")),
        (STATUS_RECUSED, _("Recused")),
        (STATUS_REMOVED, _("Removed")),
    ]
    ACTIVE_STATUSES = (STATUS_ASSIGNED, STATUS_DRAFT, STATUS_SUBMITTED)
    PENDING_STATUSES = (STATUS_ASSIGNED, STATUS_DRAFT)

    essay = models.ForeignKey(Essay, on_delete=models.CASCADE, related_name="assignments")
    judge = models.ForeignKey(User, on_delete=models.CASCADE, related_name="assignments")
    round = models.CharField(max_length=10, choices=ROUND_CHOICES, default=ROUND_INITIAL)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_ASSIGNED)
    assigned_at = models.DateTimeField(default=timezone.now)
    assigned_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    notified_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    closed_reason = models.TextField(blank=True)

    class Meta:
        # A judge reads a given essay at most once, in any round.
        constraints = [
            models.UniqueConstraint(fields=["essay", "judge"], name="one_assignment_per_judge")
        ]
        ordering = ["assigned_at", "id"]

    def __str__(self):
        return f"{self.essay.code} → {self.judge}"

    @property
    def is_active(self):
        return self.status in self.ACTIVE_STATUSES

    @property
    def is_pending(self):
        return self.status in self.PENDING_STATUSES


SCORE_VALIDATORS = [MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("10"))]


def _score_field():
    return models.DecimalField(
        max_digits=3, decimal_places=1, null=True, blank=True, validators=SCORE_VALIDATORS
    )


class ScoreSheet(models.Model):
    """One judge's judging sheet for one essay."""

    assignment = models.OneToOneField(Assignment, on_delete=models.CASCADE, related_name="sheet")

    originality = _score_field()
    clarity = _score_field()
    evidence = _score_field()
    depth = _score_field()

    originality_comment = models.TextField(blank=True)
    clarity_comment = models.TextField(blank=True)
    evidence_comment = models.TextField(blank=True)
    depth_comment = models.TextField(blank=True)
    overall_comment = models.TextField(blank=True)

    plagiarism_suspected = models.BooleanField(default=False)
    refer_ai_markers = models.BooleanField(default=False)
    refer_other = models.BooleanField(default=False)
    flag_notes = models.TextField(blank=True)

    confirmed = models.BooleanField(default=False)
    signature = models.CharField(max_length=200, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def scores(self):
        return [getattr(self, key) for key in CRITERIA_KEYS]

    @property
    def scored_count(self):
        return sum(1 for s in self.scores() if s is not None)

    @property
    def total(self):
        scores = [s for s in self.scores() if s is not None]
        return sum(scores, Decimal("0")) if scores else None

    @property
    def average(self):
        scores = [s for s in self.scores() if s is not None]
        return sum(scores, Decimal("0")) / len(scores) if scores else None

    def comment_texts(self):
        return [getattr(self, f"{key}_comment") for key in CRITERIA_KEYS] + [self.overall_comment]


class Referral(models.Model):
    KIND_AI = "ai_markers"
    KIND_STANDPOINT = "standpoint"
    KIND_PLAGIARISM = "plagiarism"
    KIND_OTHER = "other"
    KIND_CHOICES = [
        (KIND_AI, _("Unambiguous AI markers")),
        (KIND_STANDPOINT, _("Personal standpoint — recused")),
        (KIND_PLAGIARISM, _("Suspected plagiarism")),
        (KIND_OTHER, _("Other")),
    ]

    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name="referrals")
    kind = models.CharField(max_length=12, choices=KIND_CHOICES)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    resolution = models.TextField(blank=True)

    class Meta:
        ordering = ["resolved_at", "-created_at"]

    @property
    def is_open(self):
        return self.resolved_at is None


# --------------------------------------------------------------------------
# Logs
# --------------------------------------------------------------------------


class AuditLog(models.Model):
    actor = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=60, db_index=True)
    target = models.CharField(max_length=120, blank=True)
    detail = models.TextField(blank=True)
    ip = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class EmailLog(models.Model):
    to = models.CharField(max_length=254)
    kind = models.CharField(max_length=30)
    subject = models.CharField(max_length=300)
    ok = models.BooleanField(default=True)
    error = models.TextField(blank=True)
    # Lets scheduled reminders be sent exactly once per judge and deadline.
    dedupe_key = models.CharField(max_length=200, blank=True, db_index=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at", "-id"]


def default_token_lifetime():
    return timedelta(days=ContestSettings.load().invite_valid_days)
