"""This year's contest: prompts, categories and published rules."""

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from portal import contest
from portal.models import ContestSettings, Essay, IntakeRecord, Prompt
from portal.services import intake

from .factories import LOREM, MediaMixin, make_admin, make_essay, make_judge, make_pdf, upload


class LoadContestTests(TestCase):
    def test_loads_the_six_published_prompts(self):
        call_command("load_contest", verbosity=0)
        prompts = list(Prompt.objects.all())
        self.assertEqual([p.roman for p in prompts], ["I", "II", "III", "IV", "V", "VI"])
        self.assertEqual([p.category for p in prompts], ["hs"] * 3 + ["ug"] * 3)
        self.assertEqual(str(prompts[3]), "IV. Prospective Policy Analysis")
        self.assertTrue(
            prompts[0].text.startswith("Compare U.S. and Chinese approaches to AI governance")
        )
        self.assertTrue(all(p.title_zh and p.text_zh for p in prompts))
        config = ContestSettings.load()
        self.assertEqual(
            (config.word_limit, config.contact_email), (1500, "contact@dukeunccls.com")
        )
        self.assertIn("2026", config.contest_name)

    def test_restarting_never_overwrites_edits(self):
        call_command("load_contest", verbosity=0)
        Prompt.objects.filter(number=1).update(title="Edited by the committee")
        call_command("load_contest", "--if-empty", verbosity=0)
        self.assertEqual(Prompt.objects.get(number=1).title, "Edited by the committee")
        self.assertEqual(Prompt.objects.count(), 6)

    def test_roman_numerals(self):
        self.assertEqual(
            [contest.roman(n) for n in (1, 4, 6, 9, 14)], ["I", "IV", "VI", "IX", "XIV"]
        )
        self.assertEqual(
            [contest.from_roman(t) for t in ("iv", "VI", "IIII", "abc", "")],
            [4, 6, None, None, None],
        )

    def test_prompt_references_in_the_spreadsheet(self):
        call_command("load_contest", verbosity=0)
        for reference, number in (
            ("IV", 4),
            ("Prompt iv", 4),
            ("4", 4),
            ("ii.", 2),
            ("Climate and Cooperation", 3),
        ):
            self.assertEqual(intake.resolve_prompt(reference).number, number, reference)
        self.assertIsNone(intake.resolve_prompt("Something else"))


class CategoryRuleTests(MediaMixin, TestCase):
    def setUp(self):
        super().setUp()
        call_command("load_contest", verbosity=0)

    def _stored(self, name, level, prompt):
        IntakeRecord.objects.create(
            filename_key=name,
            filename=name,
            author_name="Wei Zhang",
            division=level,
            prompt_ref=prompt,
        )
        essay, _outcome = intake.create_essay_from_upload(
            upload(name, make_pdf([LOREM * 3, LOREM * 3])), division="hs", prompt=None, user=None
        )
        return essay

    def test_an_essay_is_judged_in_the_category_of_its_prompt(self):
        essay = self._stored("a.pdf", "hs", "V")
        self.assertEqual((essay.author_level, essay.division, essay.prompt.number), ("hs", "ug", 5))
        self.assertNotIn("undergraduate_in_hs_category", [f["kind"] for f in essay.flags])
        # Changing the prompt by hand moves the essay with it.
        essay.prompt = Prompt.objects.get(number=2)
        essay.save()
        self.assertEqual(Essay.objects.get(pk=essay.pk).division, "hs")

    def test_an_undergraduate_on_a_high_school_prompt_is_flagged(self):
        essay = self._stored("b.pdf", "ug", "II")
        self.assertEqual((essay.author_level, essay.division), ("ug", "hs"))
        self.assertIn("undergraduate_in_hs_category", [f["kind"] for f in essay.flags])

    def test_essays_well_over_the_word_limit_are_flagged(self):
        long_essay, _outcome = intake.create_essay_from_upload(
            upload("long.pdf", make_pdf([LOREM * 6] * 9)), division="ug", prompt=None, user=None
        )
        flag = next(f for f in long_essay.flags if f["kind"] == "over_word_limit")
        self.assertEqual(flag["limit"], 1500)
        self.assertGreater(flag["count"], 1875)
        short = self._stored("short.pdf", "ug", "IV")
        self.assertNotIn("over_word_limit", [f["kind"] for f in short.flags])


class PagesTests(TestCase):
    def setUp(self):
        call_command("load_contest", verbosity=0)

    def test_judges_see_the_prompts_and_the_brief(self):
        judge = make_judge(onboarded=False)
        self.client.force_login(judge)
        statement = self.client.get(reverse("judge_onboarding"))
        self.assertContains(statement, "IV. Prospective Policy Analysis — Imagine writing, in 2032")
        make_judge("Signed Judge")
        self.client.force_login(make_judge("Other Judge"))
        page = self.client.get(reverse("judge_rubric"))
        self.assertContains(page, "Essays may be up to 1,500 words")
        self.assertContains(page, "Digital Sovereignty and Governance")
        self.assertContains(page, "contact@dukeunccls.com")
        self.client.cookies["django_language"] = "zh-hans"
        page = self.client.get(reverse("judge_rubric"))
        self.assertContains(page, "数字主权与治理")
        self.assertContains(page, "不超过 1,500 词")

    def test_sheet_shows_the_question_being_answered(self):
        judge = make_judge()
        essay = make_essay(prompt=Prompt.objects.get(number=6))
        self.assertEqual(essay.division, "ug")
        from portal.models import Assignment

        Assignment.objects.create(essay=essay, judge=judge)
        self.client.force_login(judge)
        page = self.client.get(reverse("judge_sheet", args=[essay.code]))
        self.assertContains(page, "VI. Digital Sovereignty and Governance")
        self.assertContains(
            page, "propose governance frameworks that are both innovative and realistic"
        )

    def test_admin_pages(self):
        self.client.force_login(make_admin())
        settings_page = self.client.get(reverse("manage_settings"))
        self.assertContains(settings_page, "November 9, 2026")
        self.assertContains(settings_page, 'value="1500"')
        self.assertContains(
            self.client.get(reverse("manage_prompts")), "Middle Powers and Strategic Adaptation"
        )
        essay = make_essay(prompt=Prompt.objects.get(number=1), author_level="hs")
        self.assertContains(
            self.client.get(reverse("manage_essay", args=[essay.pk])), "Author is a"
        )
