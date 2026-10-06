import random
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from portal.models import (
    Assignment,
    ContestSettings,
    Essay,
    JudgeAttestation,
    Prompt,
    Referral,
    ScoreSheet,
    User,
)
from portal.services import assignment as assigner
from portal.services import intake
from django.core.files.uploadedfile import SimpleUploadedFile

from portal.demo_pdf import essay_pdf

PASSWORD = "demo-password-2026"

AUTHORS = [
    ("Wei Zhang", "Riverside High School", "hs"), ("Ana Ruiz", "Lakeside Academy", "hs"),
    ("Li Na", "Beijing No. 4 High School", "hs"), ("Samuel Okafor", "Durham School of the Arts", "hs"),
    ("Priya Nair", "East Chapel Hill High School", "hs"), ("Tomás Silva", "Carrboro High School", "hs"),
    ("Hannah Kim", "Duke University", "ug"), ("Marcus Reed", "University of North Carolina", "ug"),
    ("Chen Yu", "Peking University", "ug"), ("Sofia Bianchi", "Bocconi University", "ug"),
    ("Daniel Cohen", "Georgetown University", "ug"), ("Aisha Rahman", "University of Toronto", "ug"),
]  # fmt: skip
PARAGRAPHS = [
    "Export controls on advanced chips slow China's progress in the short term, but they also give Beijing a stronger incentive to subsidize domestic fabs. The policy's effect therefore depends on whether the United States can widen the gap faster than China can close it, and on whether allies continue to align their own licensing rules with Washington's.",
    "Beijing's own 2024 Government Work Report dropped the slogan that housing is for living, not speculation, for the first time since 2016. That omission is a signal that the leadership now sees the property downturn, rather than speculation, as the greater risk to stability, and it changes how local governments are expected to behave.",
    "Middle powers are not passive in this contest. Their procurement decisions, standards bodies and investment screening regimes shape the options available to both capitals. A government that hedges successfully does so by making itself costly to coerce rather than by declaring neutrality.",
    "The strongest objection to this argument is that industrial policy has a poor record of picking winners. Yet the relevant comparison is not with an idealized market but with the subsidy regimes that competitors already operate, and on that comparison the case for selective support is considerably stronger.",
    "None of this means the outcome is settled. The same evidence that points to resilience also reveals fragility: local government financing vehicles carry debts that cannot be serviced from land sales, and demographic decline narrows the window in which reform is affordable.",
]
COMMENTS = [
    "The argument is distinct from the usual framing and is sustained consistently throughout the essay, with a clear thesis stated early.",
    "The writing is clear and largely free of language errors, although the thesis could be narrowed to allow deeper treatment of the central claim.",
    "Key claims are supported with specific and accurate evidence, including one primary source, but several statistics are dropped in without explanation.",
    "The essay explains mechanisms rather than only describing events and engages with one serious counterargument, though second-order effects are thin.",
]


class Command(BaseCommand):
    help = "Fill a development database with made-up judges, essays and scores."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                "seed_demo only runs with DEBUG=1; it creates accounts with a known password."
            )
        rng = random.Random(2026)
        config = ContestSettings.load()
        config.initial_deadline = timezone.now() + timedelta(days=9)
        config.save()

        admin = User.objects.filter(role=User.ROLE_ADMIN).first() or User.objects.create_user(
            "admin@example.test", full_name="Diego Admin", role=User.ROLE_ADMIN
        )
        admin.set_password(PASSWORD)
        admin.save()

        call_command("load_contest")
        prompts = {prompt.number: prompt for prompt in Prompt.objects.all()}
        judges = []
        names = [
            "Grace Liu",
            "Robert Hayes",
            "Mei Tanaka",
            "Omar Farouk",
            "Elena Petrova",
            "James Wu",
        ]
        for index, name in enumerate(names):
            email = name.lower().replace(" ", ".") + "@example.test"
            judge = User.objects.filter(email=email).first() or User.objects.create_user(
                email, PASSWORD, full_name=name, role=User.ROLE_JUDGE, affiliation="Demo University"
            )
            if index < 5 and not judge.is_onboarded:  # the sixth has not signed yet
                attestation = JudgeAttestation.objects.create(user=judge, signed_name=name)
                if index == 1:
                    attestation.conflict_prompts.add(prompts[2])
            judges.append(judge)
        pending_invite = User.objects.filter(email="invited.judge@example.test").first()
        if not pending_invite:
            User.objects.create_user(
                "invited.judge@example.test", full_name="Nora Invited", role=User.ROLE_JUDGE
            )

        essays = []
        for index, (name, school, division) in enumerate(AUTHORS):
            # High school authors answer I–III, undergraduates IV–VI; one high
            # school author takes an undergraduate prompt, as the rules allow.
            number = index % 3 + (1 if division == "hs" and index != 5 else 4)
            prompt = prompts[number]
            surname = name.split()[-1]
            body = [rng.choice(PARAGRAPHS) for _ in range(8)]
            body[2] += f" As a student at {school}, I have watched this debate closely."
            if index % 4 == 0:
                body.append(f"Acknowledgements: I thank my teacher for comments. - {name}")
            data = essay_pdf(
                body,
                title_page=[prompt.title, name, school, "September 2026"]
                if index % 2 == 0
                else None,
                header=surname if index % 3 else None,
                footnotes={
                    1: "State Council, Report on the Work of the Government (Beijing, 2024), 14, "
                    "https://www.gov.cn/zhengce/content/202403/content_6939153.htm.",
                    4: "Barry Naughton, The Rise of China's Industrial Policy, 1978 to 2020 "
                    "(Mexico City: UNAM, 2021), 45-47.",
                },
                bibliography=[
                    "Naughton, Barry. The Rise of China's Industrial Policy, 1978 to 2020. "
                    "Mexico City: Universidad Nacional Autonoma de Mexico, 2021.",
                    "World Bank. China Economic Update. Washington, DC, 2023. https://www.worldbank.org"
                    "/en/country/china/publication/china-economic-update-december-2023.",
                ],
                author=name,
            )
            filename = f"{name.replace(' ', '_')}_essay.pdf"
            intake.IntakeRecord.objects.update_or_create(
                filename_key=intake.filename_key(filename),
                defaults={
                    "filename": filename,
                    "author_name": name,
                    "author_email": name.lower().replace(" ", ".") + "@mail.example",
                    "author_school": school,
                    "division": division,
                    "prompt_ref": prompt.roman,
                },
            )
            essay, outcome = intake.create_essay_from_upload(
                SimpleUploadedFile(filename, data), division=division, prompt=prompt, user=admin
            )
            if outcome == "created":
                essays.append(essay)

        # Release all but three, leaving something in the review queue. A real
        # reviewer would look at each one; here the outlined names are simply
        # switched on.
        for essay in essays[:-3]:
            for box in essay.redactions:
                if box["kind"] in ("name_part", "self"):
                    box["on"] = True
            intake.recompute(essay)
            intake.write_release(essay)
            essay.status = Essay.STATUS_APPROVED
            essay.approved_by = admin
            essay.approved_at = timezone.now()
            essay.save()

        created, _unfilled = assigner.auto_assign(actor=admin, rng=rng)
        for number, assignment in enumerate(created):
            roll = rng.random()
            if roll < 0.2:
                continue
            base = rng.choice([4.5, 5.5, 6, 6.5, 7, 7.5, 8, 8.5])
            scores = [min(10, max(0, base + rng.choice([-1, -0.5, 0, 0.5, 1]))) for _ in range(4)]
            if number % 9 == 0:
                scores = [max(0, s - 3) for s in scores]  # manufacture a divergence
            sheet = ScoreSheet.objects.create(
                assignment=assignment,
                originality=Decimal(str(scores[0])),
                clarity=Decimal(str(scores[1])),
                evidence=Decimal(str(scores[2])),
                depth=Decimal(str(scores[3])),
                originality_comment=COMMENTS[0],
                clarity_comment=COMMENTS[1],
                evidence_comment=COMMENTS[2],
                depth_comment=COMMENTS[3],
                confirmed=roll >= 0.35,
                signature=assignment.judge.full_name if roll >= 0.35 else "",
            )
            if roll < 0.35:
                assignment.status = Assignment.STATUS_DRAFT
                assignment.started_at = timezone.now()
            else:
                assignment.status = Assignment.STATUS_SUBMITTED
                assignment.submitted_at = timezone.now() - timedelta(hours=rng.randint(1, 72))
                if number % 11 == 0:
                    sheet.refer_ai_markers = True
                    sheet.flag_notes = (
                        "The second footnote cites a report I could not find anywhere."
                    )
                    sheet.save()
                    Referral.objects.create(
                        assignment=assignment, kind=Referral.KIND_AI, notes=sheet.flag_notes
                    )
            assignment.save()

        self.stdout.write(
            self.style.SUCCESS(
                f"Demo data ready. Sign in as admin@example.test or grace.liu@example.test "
                f"with the password {PASSWORD}"
            )
        )
