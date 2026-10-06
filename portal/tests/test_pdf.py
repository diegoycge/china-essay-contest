"""The PDF pipeline: rendering, automatic redaction, release, intake."""

import re
from pathlib import Path

from django.test import SimpleTestCase, TestCase

import portal
from portal.models import Essay, IntakeRecord
from portal.services import anonymize as anon
from portal.services import intake, pdf, redaction
from portal.services.text import count_words

from .factories import LOREM, MediaMixin, make_pdf, simple_pdf, upload

NOTE = (
    "State Council, Report on the Work of the Government (Beijing, 2024), 14, "
    "http://www.xinhuanet.com/politics/2021-03/13/c_13912345678.htm."
)


def essay_file(**options):
    defaults = {
        "title_page": [
            "Chips and Power",
            "Wei Zhang",
            "Riverside High School",
            "wz@school.example",
        ],
        "header": "Zhang",
        "footnotes": {0: NOTE},
        "bibliography": ["Naughton, Barry. The Rise of China's Industrial Policy. UNAM, 2021."],
        "author": "Wei Zhang",
    }
    defaults.update(options)
    body = [
        LOREM * 2,
        LOREM * 2 + "As a student at Riverside High School, I follow this closely.",
        LOREM * 2 + "Premier Li Qiang and Zhang Yiming were both cited. Call 919-555-0142.",
        LOREM * 3,
    ]
    return make_pdf(body, **defaults)


def stored(name="essay.pdf", data=None, **author):
    for key, value in author.items():
        IntakeRecord.objects.update_or_create(
            filename_key=name.lower(), defaults={"filename": name, key: value}
        )
    return intake.create_essay_from_upload(
        upload(name, data or essay_file()), division="hs", prompt=None, user=None
    )


class WordCountTests(SimpleTestCase):
    def test_english_and_chinese(self):
        self.assertEqual(count_words("The essay's well-argued point."), 4)
        self.assertEqual(count_words("论点清晰，论据充分。"), 8)
        self.assertEqual(count_words("论点 clear and 充分"), 6)
        self.assertEqual(count_words(""), 0)


class RenderTests(MediaMixin, TestCase):
    def test_pages_and_word_positions(self):
        essay, outcome = stored()
        self.assertEqual(outcome, "created")
        self.assertEqual(essay.status, Essay.STATUS_REVIEW)
        self.assertGreaterEqual(essay.page_count, 3)
        layout = pdf.load_layout(essay.work_dir)
        self.assertEqual(len(layout["pages"]), essay.page_count)
        for number in range(1, essay.page_count + 1):
            self.assertTrue(
                pdf.work_page(essay.work_dir, number).read_bytes().startswith(b"\x89PNG")
            )
        text, _starts = redaction.page_text(layout["pages"][1]["tokens"])
        self.assertIn("Export controls on advanced chips", text)
        for token in layout["pages"][1]["tokens"]:
            self.assertTrue(
                0 <= token[1] <= token[3] <= 1 and 0 <= token[2] <= token[4] <= 1, token
            )
        self.assertEqual(essay.meta_authors, ["Wei Zhang"])

    def test_title_page_is_left_out_and_file_name_is_not_kept(self):
        essay, _outcome = stored("Zhang_Wei.pdf")
        self.assertEqual(essay.dropped_pages, [0])
        self.assertIn("pages_dropped", [f["kind"] for f in essay.flags])
        self.assertNotIn("zhang", essay.original_file.name.lower())
        self.assertRegex(essay.code, r"^E-[A-Z2-9]{5}$")

    def test_what_cannot_be_processed_is_kept_and_explained(self):
        for name, data, code in (
            ("garbage.pdf", b"%PDF-1.4\nthis is not really a pdf", "unreadable"),
            ("long.pdf", simple_pdf([["line"]] * 61), "too_many_pages"),
        ):
            essay, outcome = stored(name, data)
            self.assertEqual(
                (outcome, essay.status, essay.extraction_note), ("failed", "failed", code)
            )
            self.assertEqual(essay.work_dir, "")
        self.assertEqual(list((Path(self.media) / "work").glob("*")), [])

    def test_only_pdfs_are_accepted(self):
        for name, data in (("essay.docx", b"PK\x03\x04"), ("essay.pdf", b"PK\x03\x04 pretending")):
            with self.assertRaises(intake.IntakeError):
                intake.create_essay_from_upload(
                    upload(name, data), division="ug", prompt=None, user=None
                )
        self.assertFalse(Essay.objects.exists())

    def test_a_file_that_exhausts_the_time_limit_fails_cleanly(self):
        with self.settings(PDF_TIMEOUT_SECONDS=0.001):
            essay, outcome = stored()
        self.assertEqual((outcome, essay.extraction_note), ("failed", "too_complex"))
        self.assertEqual(list((Path(self.media) / "work").glob("*")), [])


class AutoRedactionTests(MediaMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.essay, _outcome = stored(
            author_name="Wei Zhang", author_school="Riverside High School"
        )
        self.layout = pdf.load_layout(self.essay.work_dir)

    def kinds(self, on):
        return sorted({box["kind"] for box in self.essay.redactions if box["on"] is on})

    def test_known_identity_is_boxed(self):
        self.assertEqual(self.kinds(True), ["header", "phone", "school"])
        text = self.essay.released_text
        for gone in ("Riverside", "919-555-0142", "Zhang 1", "Zhang 2"):
            self.assertNotIn(gone, text)
        self.assertEqual(intake.release_problems(self.essay), [])

    def test_surname_alone_is_only_outlined(self):
        # "Zhang" could be the author or (here) Zhang Yiming; "Li" is not the author at all.
        self.assertEqual(self.kinds(False), ["name_part", "self"])
        self.assertIn("Li Qiang and Zhang Yiming", self.essay.released_text)
        flags = {f["kind"]: f for f in self.essay.flags}
        self.assertEqual(flags["name_part_present"]["term"], "Zhang")

    def test_citations_are_left_whole(self):
        text = self.essay.released_text
        self.assertIn("c_13912345678.htm", text)  # digits in a link are not a phone number
        self.assertIn("State Council, Report on the Work of the Government", text)
        self.assertIn("Naughton, Barry.", text)

    def test_author_on_the_first_page_without_a_title_page(self):
        data = make_pdf(
            ["Name: Ana Ruiz", "School: Lakeside Academy", "By Ana Ruiz", LOREM * 3, LOREM * 3],
            author="Ana Ruiz",
        )
        essay, _outcome = stored("ruiz.pdf", data)  # no author record at all
        self.assertEqual(essay.dropped_pages, [])
        self.assertNotIn("Ana Ruiz", essay.released_text)
        self.assertNotIn("Lakeside", essay.released_text)
        self.assertIn("no_author_on_record", [f["kind"] for f in essay.flags])

    def test_new_author_details_keep_the_reviewers_own_work(self):
        essay = self.essay
        manual = {"p": 1, "x": 0.1, "y": 0.5, "w": 0.2, "h": 0.03, "kind": "manual", "on": True}
        switched_off = next(b for b in essay.redactions if b["kind"] == "school")
        switched_off["on"] = False
        essay.redactions.append(manual)
        essay.author_school = "Riverside High School"
        intake.run_auto_redaction(essay)
        self.assertIn(manual, essay.redactions)
        again = next(b for b in essay.redactions if b["kind"] == "school")
        self.assertFalse(again["on"])
        intake.run_auto_redaction(essay, reset=True)
        self.assertNotIn(manual, essay.redactions)

    def test_redact_a_word_everywhere(self):
        found = redaction.term_redactions(
            self.layout, "Zhang Yiming", set(self.essay.dropped_pages)
        )
        self.assertEqual(len(found), 1)
        self.essay.redactions += found
        intake.recompute(self.essay)
        self.assertNotIn("Yiming", self.essay.released_text)
        self.assertEqual(redaction.term_redactions(self.layout, "Nonexistent", set()), [])


class SyntheticLayoutTests(SimpleTestCase):
    """Cases the Courier test PDFs cannot produce."""

    def page(self, *tokens):
        return {"pages": [{"w": 612, "h": 792, "tokens": [list(t) for t in tokens]}]}

    def test_chinese_names_are_matched_character_by_character(self):
        chars = "作者张伟认为这很重要"
        tokens = [
            (ch, 0.1 + i * 0.03, 0.2, 0.13 + i * 0.03, 0.22, "", 0) for i, ch in enumerate(chars)
        ]
        layout = self.page(*tokens)
        boxes = redaction.auto_redactions(layout, author_name="张伟")
        self.assertEqual([(b["kind"], b["on"]) for b in boxes], [("name", True)])
        self.assertAlmostEqual(boxes[0]["x"], 0.16, places=2)
        self.assertAlmostEqual(boxes[0]["w"], 0.06, places=2)
        self.assertEqual(
            redaction.released_pages(layout, boxes, set()), ["作者[REDACTED] 认为这很重要"]
        )

    def test_a_name_split_across_two_lines_gets_a_box_on_each(self):
        layout = self.page(
            ("see", 0.1, 0.2, 0.12, 0.22, " ", 0),
            ("Wei", 0.8, 0.2, 0.85, 0.22, "\n", 0),
            ("Zhang", 0.1, 0.24, 0.17, 0.26, " ", 1),
            ("here.", 0.18, 0.24, 0.24, 0.26, "\n", 1),
        )
        boxes = redaction.auto_redactions(layout, author_name="Wei Zhang")
        self.assertEqual(sorted(b["y"] for b in boxes if b["on"]), [0.2, 0.24])
        self.assertEqual(
            redaction.released_pages(layout, boxes, set()), ["see [REDACTED]\n[REDACTED] here."]
        )

    def test_posted_boxes_are_validated(self):
        raw = [
            {"p": 0, "x": 0.1, "y": 0.1, "w": 0.2, "h": 0.05, "kind": "manual", "on": True},
            {
                "p": 0,
                "x": 0.9,
                "y": 0.9,
                "w": 5,
                "h": 5,
                "kind": "name",
                "on": False,
                "t": "x" * 500,
            },
            {"p": 7, "x": 0.1, "y": 0.1, "w": 0.2, "h": 0.05, "kind": "manual", "on": True},
            {"p": 0, "x": "nope"},
            {"p": 0, "x": 0.1, "y": 0.1, "w": 0.2, "h": 0.05, "kind": "manual", "on": False},
            "junk",
        ]
        cleaned = redaction.clean(raw, page_count=1)
        self.assertEqual(len(cleaned), 2)
        self.assertEqual((cleaned[1]["w"], cleaned[1]["h"], len(cleaned[1]["t"])), (0.1, 0.1, 60))
        self.assertEqual(redaction.clean("junk", 1), [])

    def test_identity_patterns(self):
        self.assertTrue(anon.is_identity_line("Name: Jane Doe"))
        self.assertTrue(anon.is_identity_line("By Jane Q. Doe"))
        self.assertFalse(anon.is_identity_line("Chips and Power"))
        self.assertEqual(
            anon.hard_leaks(
                "by Zhang, Wei of Riverside High School", "Wei Zhang", "", "Riverside High School"
            ),
            ["name", "school"],
        )
        self.assertEqual(anon.hard_leaks("write to a@b.org", "Wei Zhang"), ["any_email"])
        self.assertTrue(anon.hard_leaks("by Mary J. Smith", "Mary Smith"))


class ReleaseTests(MediaMixin, TestCase):
    def test_boxes_are_burned_into_flat_images(self):
        from PIL import Image

        essay, _outcome = stored(author_name="Wei Zhang", author_school="Riverside High School")
        school = next(b for b in essay.redactions if b["kind"] == "school")
        intake.write_release(essay)
        self.assertEqual(essay.released_pages, essay.page_count - 1)  # title page left out

        def ink(path):
            with Image.open(path) as image:
                grey = image.convert("L")
                width, height = grey.size
                region = grey.crop(
                    (
                        int(school["x"] * width) + 2,
                        int(school["y"] * height) + 2,
                        int((school["x"] + school["w"]) * width) - 2,
                        int((school["y"] + school["h"]) * height) - 2,
                    )
                )
                return region.getextrema()

        # Original page: dark text on white. Released page: solid black, nothing else.
        before = ink(pdf.work_page(essay.work_dir, school["p"] + 1))
        after = ink(pdf.released_page(essay.release_dir, school["p"]))
        self.assertGreater(before[1], 200)
        self.assertEqual(after, (0, 0))
        released = pdf.released_page(essay.release_dir, 1).read_bytes()
        self.assertNotIn(b"Zhang", released)
        self.assertNotIn(b"tEXt", released)

    def test_scans_need_the_reviewer_to_vouch_for_them(self):
        blank = simple_pdf([[""], [""]])
        essay, outcome = stored("scan.pdf", blank)
        self.assertEqual(outcome, "created")
        self.assertIn("no_text_layer", [f["kind"] for f in essay.flags])
        self.assertEqual(intake.release_problems(essay), ["no_text_layer"])


class IntakeTests(MediaMixin, TestCase):
    def test_duplicates_are_skipped(self):
        data = essay_file()
        essay, _outcome = stored("a.pdf", data)
        again, outcome = stored("copy.pdf", data)
        self.assertEqual((again.pk, outcome), (essay.pk, "duplicate"))

    def test_author_sheet_before_or_after_upload(self):
        body = [LOREM * 3 + " My mentor Wei Zhang of Riverside High School helped.", LOREM * 3]
        essay, _outcome = stored("essay-01.pdf", make_pdf(body))
        self.assertIn("Wei Zhang", essay.released_text)

        sheet = (
            "filename,name,school,division\n"
            "ESSAY-01.pdf,Wei Zhang,Riverside High School,undergraduate\n"
            "later.pdf,Ana Ruiz,Lakeside Academy,high school\n"
        )
        stats = intake.import_metadata(upload("authors.csv", sheet.encode()))
        self.assertEqual((stats["rows"], stats["matched"], stats["reprocessed"]), (2, 1, 1))
        essay.refresh_from_db()
        self.assertEqual((essay.author_name, essay.division), ("Wei Zhang", "ug"))
        self.assertNotIn("Wei Zhang", essay.released_text)
        self.assertNotIn("Riverside", essay.released_text)

        later, _outcome = stored(
            "later.pdf", make_pdf([LOREM * 3 + " Signed, Ana Ruiz.", LOREM * 3])
        )
        self.assertEqual((later.author_name, later.division), ("Ana Ruiz", "hs"))
        self.assertNotIn("Ana Ruiz", later.released_text)

    def test_deleting_an_essay_removes_every_file(self):
        essay, _outcome = stored()
        intake.write_release(essay)
        essay.save()
        intake.delete_files(essay)
        left = [p for p in Path(self.media).rglob("*") if p.is_file()]
        self.assertEqual(left, [])


class CatalogTests(SimpleTestCase):
    def test_chinese_catalog_has_no_gaps(self):
        path = Path(portal.__file__).parent / "locale" / "zh_Hans" / "LC_MESSAGES" / "django.po"
        text = path.read_text(encoding="utf-8")
        # Leftover "previous msgid" notes are rejected by the older msgfmt in the Docker image.
        self.assertNotIn("\n#|", text)
        entries = [e for e in text.split("\n\n")[1:] if not e.startswith("#~")]
        self.assertGreater(len(entries), 400)
        for entry in entries:
            self.assertNotIn("#, fuzzy", entry)
            self.assertIsNone(re.search(r'^msgstr(\[\d\])? ""\s*\Z', entry, re.M), entry)
