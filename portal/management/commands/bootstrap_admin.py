import os

from django.core.management.base import BaseCommand

from portal.models import ContestSettings, User
from portal.services import emails


class Command(BaseCommand):
    help = (
        "Create the first administrator from ADMIN_EMAIL / ADMIN_NAME (and optionally "
        "ADMIN_PASSWORD). Does nothing once any administrator exists."
    )

    def handle(self, *args, **options):
        ContestSettings.load()
        if User.objects.filter(role=User.ROLE_ADMIN).exists():
            return
        email = os.environ.get("ADMIN_EMAIL", "").strip().lower()
        if not email:
            self.stdout.write(
                self.style.WARNING(
                    "No administrator exists and ADMIN_EMAIL is not set. Set it and restart, "
                    "or run: python manage.py bootstrap_admin"
                )
            )
            return
        password = os.environ.get("ADMIN_PASSWORD", "")
        user = User.objects.create_user(
            email,
            password or None,
            full_name=os.environ.get("ADMIN_NAME", "Administrator"),
            role=User.ROLE_ADMIN,
        )
        if password:
            self.stdout.write(self.style.SUCCESS(f"Administrator {email} created."))
            return
        link = emails.issue_invite(user).link
        self.stdout.write(
            self.style.SUCCESS(
                f"Administrator {email} created. Open this one-time link to set up your sign-in (a passkey or a password):\n{link}"
            )
        )
