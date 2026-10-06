from django.core.management.base import BaseCommand

from portal.services import emails


class Command(BaseCommand):
    help = "Send any deadline reminders that are due. Safe to run repeatedly."

    def handle(self, *args, **options):
        sent = emails.send_due_reminders()
        self.stdout.write(f"{sent} reminder(s) sent.")
