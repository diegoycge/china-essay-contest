from decimal import Decimal

from django import forms
from django.contrib.auth import password_validation
from django.core.validators import MaxLengthValidator
from django.utils.translation import gettext_lazy as _

from .models import (
    CRITERIA_KEYS,
    DIVISION_CHOICES,
    ContestSettings,
    Essay,
    Prompt,
    ScoreSheet,
    User,
)

# Values keep one decimal place so they match how stored scores print ("7.0").
SCORE_CHOICES = [("", "—")] + [(f"{n / 2:.1f}", f"{n / 2:g}") for n in range(0, 21)]


def _to_score(value):
    return Decimal(value)


class LoginForm(forms.Form):
    email = forms.EmailField(label=_("Email"))
    password = forms.CharField(label=_("Password"), widget=forms.PasswordInput, strip=False)


class EmailForm(forms.Form):
    email = forms.EmailField(label=_("Email"))


class NewPasswordForm(forms.Form):
    """Choose a password (invitation or reset)."""

    password1 = forms.CharField(
        label=_("New password"),
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    password2 = forms.CharField(
        label=_("Repeat password"),
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        first, second = cleaned.get("password1"), cleaned.get("password2")
        if first and second and first != second:
            self.add_error("password2", _("The two passwords do not match."))
        elif first:
            try:
                password_validation.validate_password(first, self.user)
            except forms.ValidationError as error:
                self.add_error("password1", error)
        return cleaned

    def save(self):
        self.user.set_password(self.cleaned_data["password1"])
        self.user.save(update_fields=["password"])
        return self.user


class ChangePasswordForm(NewPasswordForm):
    current = forms.CharField(label=_("Current password"), strip=False, widget=forms.PasswordInput)
    field_order = ["current", "password1", "password2"]

    def clean_current(self):
        current = self.cleaned_data["current"]
        if not self.user.check_password(current):
            raise forms.ValidationError(_("That is not your current password."))
        return current


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["full_name", "affiliation"]
        labels = {"full_name": _("Full name"), "affiliation": _("Affiliation")}


class PromptChoices(forms.ModelMultipleChoiceField):
    """Show judges the whole question, in their language, not just its number."""

    def label_from_instance(self, prompt):
        from .templatetags.portal_tags import prompt_label, prompt_text

        text = prompt_text(prompt)
        return f"{prompt_label(prompt)} — {text}" if text else prompt_label(prompt)


class OnboardingForm(forms.Form):
    read_rubric = forms.BooleanField(
        label=_("I have read the judging rubric carefully and will apply it as written.")
    )
    no_beliefs = forms.BooleanField(
        label=_(
            "I have no significant personal beliefs on any essay question that would hinder "
            "my ability to judge fairly, other than those I have declared below."
        )
    )
    conflict_prompts = PromptChoices(
        label=_("Essay questions on which I hold significant personal beliefs"),
        queryset=Prompt.objects.filter(is_active=True),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    conflict_notes = forms.CharField(
        label=_("Anything else the committee should know (optional)"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    signed_name = forms.CharField(label=_("Type your full name to sign"), max_length=200)


MAX_COMMENT_CHARS = 20000


class ScoreSheetForm(forms.ModelForm):
    """The judging sheet. Every field is optional so drafts can be saved;
    completeness is checked separately when the judge submits."""

    originality = forms.TypedChoiceField(
        choices=SCORE_CHOICES, coerce=_to_score, empty_value=None, required=False
    )
    clarity = forms.TypedChoiceField(
        choices=SCORE_CHOICES, coerce=_to_score, empty_value=None, required=False
    )
    evidence = forms.TypedChoiceField(
        choices=SCORE_CHOICES, coerce=_to_score, empty_value=None, required=False
    )
    depth = forms.TypedChoiceField(
        choices=SCORE_CHOICES, coerce=_to_score, empty_value=None, required=False
    )

    TEXT_FIELDS = [f"{key}_comment" for key in CRITERIA_KEYS] + ["overall_comment", "flag_notes"]

    class Meta:
        model = ScoreSheet
        fields = (
            list(CRITERIA_KEYS)
            + [f"{key}_comment" for key in CRITERIA_KEYS]
            + [
                "overall_comment",
                "plagiarism_suspected",
                "refer_ai_markers",
                "refer_other",
                "flag_notes",
                "confirmed",
                "signature",
            ]
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for key in CRITERIA_KEYS:
            self.fields[f"{key}_comment"].widget.attrs.update({"rows": 5})
        self.fields["overall_comment"].widget.attrs.update({"rows": 4})
        self.fields["flag_notes"].widget.attrs.update({"rows": 3})
        for name in self.TEXT_FIELDS:
            # Generous for a justification, but bounded: every sheet's text is
            # loaded for the results pages and exports.
            self.fields[name].max_length = MAX_COMMENT_CHARS
            self.fields[name].validators.append(MaxLengthValidator(MAX_COMMENT_CHARS))
            self.fields[name].widget.attrs["maxlength"] = MAX_COMMENT_CHARS
        self.fields["signature"].widget.attrs.update({"autocomplete": "off"})


class InviteForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["full_name", "email", "affiliation", "role", "language", "max_load"]
        labels = {
            "full_name": _("Full name"),
            "email": _("Email"),
            "affiliation": _("Affiliation"),
            "role": _("Role"),
            "language": _("Language for emails"),
            "max_load": _("Maximum essays (optional)"),
        }

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(_("Someone with this email already has an account."))
        return email


class UserEditForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["full_name", "affiliation", "language", "max_load"]
        labels = {
            "full_name": _("Full name"),
            "affiliation": _("Affiliation"),
            "language": _("Language for emails"),
            "max_load": _("Maximum essays (optional)"),
        }


class PromptForm(forms.ModelForm):
    class Meta:
        model = Prompt
        fields = ["number", "division", "title", "title_zh", "text", "text_zh", "is_active"]
        labels = {
            "number": _("Number"),
            "division": _("Division"),
            "title": _("Short title"),
            "title_zh": _("Short title (Chinese)"),
            "text": _("Full question"),
            "text_zh": _("Full question (Chinese)"),
            "is_active": _("Active"),
        }
        widgets = {
            "text": forms.Textarea(attrs={"rows": 3}),
            "text_zh": forms.Textarea(attrs={"rows": 3}),
        }


class EssayMetaForm(forms.ModelForm):
    class Meta:
        model = Essay
        fields = [
            "prompt",
            "division",
            "author_name",
            "author_email",
            "author_school",
            "author_level",
            "admin_notes",
        ]
        labels = {
            "division": _("Division"),
            "prompt": _("Prompt"),
            "author_name": _("Author name"),
            "author_email": _("Author email"),
            "author_school": _("School"),
            "author_level": _("Author is a"),
            "admin_notes": _("Committee notes"),
        }
        widgets = {"admin_notes": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["prompt"].empty_label = _("— not set —")
        self.fields["author_level"].choices = [("", _("— not recorded —"))] + [
            (value, label) for value, label in DIVISION_CHOICES
        ]
        self.fields["division"].label = _("Judged in")
        self.fields["division"].help_text = _(
            "Follows the prompt: an essay answering Prompts IV–VI is judged in the undergraduate "
            "category even if a high school student wrote it."
        )


class UploadForm(forms.Form):
    division = forms.ChoiceField(label=_("Division"), choices=DIVISION_CHOICES)
    prompt = forms.ModelChoiceField(
        label=_("Prompt"),
        queryset=Prompt.objects.filter(is_active=True),
        required=False,
        empty_label=_("— not set —"),
    )


class DateTimeLocalInput(forms.DateTimeInput):
    input_type = "datetime-local"

    def __init__(self, **kwargs):
        super().__init__(format="%Y-%m-%dT%H:%M", **kwargs)


class SettingsForm(forms.ModelForm):
    class Meta:
        model = ContestSettings
        fields = [
            "contest_name",
            "contact_email",
            "word_limit",
            "initial_deadline",
            "rescore_deadline",
            "reminder_days",
            "readers_per_essay",
            "divergence_threshold",
            "rescore_method",
            "min_comment_words",
            "invite_valid_days",
        ]
        labels = {
            "contest_name": _("Contest name"),
            "contact_email": _("Contact address shown to judges"),
            "word_limit": _("Essay word limit"),
            "initial_deadline": _("Judging deadline"),
            "rescore_deadline": _("Re-score deadline"),
            "reminder_days": _("Send reminders this many days before a deadline"),
            "readers_per_essay": _("Human readers per essay"),
            "divergence_threshold": _("Divergence threshold (points)"),
            "rescore_method": _("Final score when an essay has been re-scored"),
            "min_comment_words": _("Minimum words of justification"),
            "invite_valid_days": _("Invitation links expire after (days)"),
        }
        help_texts = {
            "reminder_days": _("Comma-separated, for example 3,1. Leave empty to send none."),
            "divergence_threshold": _(
                "An essay is flagged for re-scoring when the gap between any two readers' "
                "average scores is at least this large."
            ),
            "rescore_deadline": _(
                "When empty, the judging deadline applies until it has passed; after that "
                "re-scores have no deadline."
            ),
        }
        widgets = {
            "initial_deadline": DateTimeLocalInput(),
            "rescore_deadline": DateTimeLocalInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("initial_deadline", "rescore_deadline"):
            self.fields[name].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"]

    def clean_reminder_days(self):
        value = self.cleaned_data["reminder_days"].replace("，", ",").replace(" ", "")
        if value and not all(part.isdigit() and int(part) > 0 for part in value.split(",")):
            raise forms.ValidationError(_("Use whole numbers separated by commas."))
        return value

    def clean_divergence_threshold(self):
        value = self.cleaned_data["divergence_threshold"]
        if value * 2 != int(value * 2):
            raise forms.ValidationError(_("Use steps of 0.5."))
        return value
