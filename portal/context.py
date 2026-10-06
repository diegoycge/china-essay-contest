from django.conf import settings

from .models import ContestSettings, Essay, Referral

NAV_SECTIONS = {
    "manage_dashboard": "dashboard",
    "manage_essays": "essays",
    "manage_essay": "essays",
    "manage_sheet": "essays",
    "manage_preview": "essays",
    "manage_upload": "upload",
    "manage_review": "review",
    "manage_users": "users",
    "manage_user": "users",
    "manage_assignments": "assignments",
    "manage_divergence": "divergence",
    "manage_referrals": "referrals",
    "manage_results": "results",
    "manage_prompts": "prompts",
    "manage_prompt": "prompts",
    "manage_settings": "settings",
    "manage_logs": "logs",
    "judge_dashboard": "essays",
    "judge_sheet": "essays",
    "judge_rubric": "rubric",
}


def portal(request):
    match = getattr(request, "resolver_match", None)
    context = {
        "contest": ContestSettings.load(),
        "nav": NAV_SECTIONS.get(match.url_name, "") if match else "",
        "email_configured": settings.EMAIL_CONFIGURED,
    }
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated and user.is_admin:
        context["nav_review_count"] = Essay.objects.filter(
            status__in=(Essay.STATUS_REVIEW, Essay.STATUS_FAILED)
        ).count()
        context["nav_referral_count"] = Referral.objects.filter(resolved_at__isnull=True).count()
    return context
