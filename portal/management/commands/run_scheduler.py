import logging
import time
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import DatabaseError, close_old_connections
from django.utils import timezone

from portal.models import AccessToken, ContestSettings, LoginAttempt
from portal.services import emails

logger = logging.getLogger("portal.scheduler")


class Command(BaseCommand):
    help = "Long-running loop: sends due deadline reminders and prunes stale security rows."

    def add_arguments(self, parser):
        parser.add_argument("--interval", type=int, default=900, help="Seconds between runs.")

    def handle(self, *args, **options):
        interval = options["interval"]
        # On first start the web container may still be creating the tables.
        while True:
            try:
                ContestSettings.objects.exists()
                break
            except DatabaseError:
                logger.info("Waiting for the database to be migrated…")
                close_old_connections()
                time.sleep(5)
        logger.info("Scheduler started; checking every %s seconds.", interval)
        while True:
            try:
                close_old_connections()
                sent = emails.send_due_reminders()
                if sent:
                    logger.info("%s reminder(s) sent.", sent)
                cutoff = timezone.now() - timedelta(days=30)
                LoginAttempt.objects.filter(created_at__lt=cutoff).delete()
                AccessToken.objects.filter(expires_at__lt=cutoff).delete()
            except Exception:  # keep the loop alive through transient database errors
                logger.exception("Scheduler run failed; will retry.")
            time.sleep(interval)
