from django.conf import settings

from ..models import AuditLog


def client_ip(request):
    if request is None:
        return ""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "") if settings.BEHIND_PROXY else ""
    if forwarded:
        # The last entry is the one our own proxy appended; earlier entries
        # are supplied by the client and can be forged.
        return forwarded.split(",")[-1].strip()[:64]
    return request.META.get("REMOTE_ADDR", "")[:64]


def log(request, action, target="", detail="", actor=None):
    """Record a security- or integrity-relevant event."""
    if actor is None and request is not None and request.user.is_authenticated:
        actor = request.user
    AuditLog.objects.create(
        actor=actor,
        action=action,
        target=str(target)[:120],
        detail=detail,
        ip=client_ip(request),
    )
