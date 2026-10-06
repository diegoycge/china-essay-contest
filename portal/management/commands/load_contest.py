from django.core.management.base import BaseCommand

from portal import contest
from portal.models import ContestSettings, Prompt


class Command(BaseCommand):
    help = (
        "Load this year's prompts and basic facts (name, word limit, contact address) from "
        "portal/contest.py. With --if-empty it does nothing once any prompt exists, so "
        "changes made in the portal are never overwritten on restart."
    )

    def add_arguments(self, parser):
        parser.add_argument("--if-empty", action="store_true")

    def handle(self, *args, **options):
        if options["if_empty"] and Prompt.objects.exists():
            return
        for number, category, title, title_zh, text, text_zh in contest.PROMPTS:
            Prompt.objects.update_or_create(
                number=number,
                defaults={
                    "division": category,
                    "title": title,
                    "title_zh": title_zh,
                    "text": text,
                    "text_zh": text_zh,
                    "is_active": True,
                },
            )
        config = ContestSettings.load()
        config.contest_name = contest.CONTEST_NAME
        config.word_limit = contest.WORD_LIMIT
        config.contact_email = contest.CONTACT_EMAIL
        config.save()
        self.stdout.write(
            self.style.SUCCESS(f"Loaded {len(contest.PROMPTS)} prompts for {config.contest_name}.")
        )
