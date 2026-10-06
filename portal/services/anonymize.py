"""What counts as an identifying detail in an essay's text.

This module only finds things; services/redaction.py turns what it finds
into boxes on the page. It is a first pass, not a guarantee: every essay
still goes through an admin's review before judges can see it.

The rules are deliberately conservative about what is redacted outright.
Exact matches on what we know about the author (full name, school, email) are
redacted; anything fuzzier — a surname on its own, a phrase like "at my
school" — is only suggested to the reviewer, because in essays about China a
surname such as Li, Wang or Xi is as likely to be a politician as the author.
"""

import re

from .text import CJK

REDACTED = "[REDACTED]"

# Bounded repeats: an unbounded `+` before the `@` is quadratic on a long run
# of letters, which a crafted file could use to stall a worker.
EMAIL_RE = re.compile(
    r"(?<![A-Za-z0-9._%+\-])[A-Za-z0-9._%+\-]{1,64}@[A-Za-z0-9.\-]{1,253}\.[A-Za-z]{2,24}"
)
PHONE_RE = re.compile(
    r"(?<![\d.])(?:\+?\d{1,3}[\s.\-])?\(?\d{3}\)?[\s.\-]\d{3,4}[\s.\-]\d{4}(?!\d)"
    r"|(?<!\d)1[3-9]\d{9}(?!\d)"
)

# "Name: Jane Doe" style lines that appear at the top of a submission.
LABEL_LINE_RE = re.compile(
    r"^\s*(?:(?:full\s+|author'?s?\s+|student'?s?\s+|legal\s+)?name|author|student(?:\s+id)?"
    r"|submitted\s+by|written\s+by|school|high\s+school|university|college|institution"
    r"|affiliation|e-?mail|phone|tel|grade|class(?:\s+of)?|year|major|teacher|instructor"
    r"|professor|advis[oe]r|mentor|address|city|hometown|wechat|division"
    r"|姓名|作者|学生|学校|院校|大学|中学|邮箱|电子邮件|电话|手机|年级|班级|专业|指导老师|指导教师|导师|微信)"
    r"\s*[:：]",
    re.IGNORECASE,
)
BYLINE_RE = re.compile(
    r"^\s*(?:by|written by|submitted by|作者)[\s:：]+\S+(?:\s+\S+){0,4}\s*$", re.IGNORECASE
)

# Phrases where authors tend to say who or where they are.
SELF_REFERENCE_PATTERNS = [
    r"\bmy name is\b",
    r"\bI am a (?:\w+ ){0,3}(?:student|senior|junior|sophomore|freshman|major)\b",
    r"\bI'?m a (?:\w+ ){0,3}(?:student|senior|junior|sophomore|freshman|major)\b",
    r"\bas a (?:\w+ ){0,3}(?:student|senior|junior|sophomore|freshman) (?:at|in|from|of)\b",
    r"\b(?:at|in|from) my (?:school|high school|university|college|hometown|home town)\b",
    r"\bmy (?:school|high school|university|college|hometown|professor|teacher|classmates?)\b",
    r"\bI (?:attend|study at|go to|grew up in|was born in|live in)\b",
    r"\bwhere I (?:study|live|grew up|go to school)\b",
    r"我叫",
    r"我是[^。，,.]{0,12}(?:学生|大学生|高中生|本科生)",
    r"我(?:就读|来自|出生|生活|成长)",
    r"我的(?:学校|大学|高中|家乡|老师)",
]
SELF_REFERENCE_RE = re.compile("|".join(SELF_REFERENCE_PATTERNS), re.IGNORECASE)
ACKNOWLEDGEMENT_RE = re.compile(
    r"^\s*(acknowledge?ments?|致谢)\s*:?\s*$", re.IGNORECASE | re.MULTILINE
)

SCHOOL_STOPWORDS = {
    "university", "college", "school", "high", "middle", "senior", "junior", "academy",
    "institute", "institution", "of", "the", "at", "and", "for", "in", "international",
    "national", "state", "public", "private", "day", "prep", "preparatory", "secondary",
    "no", "st", "saint", "new", "north", "south", "east", "west", "central", "campus",
    "affiliated", "experimental", "foreign", "language", "languages", "science",
    "technology", "china", "chinese", "american", "america", "united", "states",
}  # fmt: skip

OPENING_SCAN_LINES = 15
MAX_LABEL_LINE = 200
PAGE_NUMBER_RE = re.compile(
    r"^(page\s*)?[-–—\s]*\d{1,3}[-–—\s]*((of|/)\s*\d{1,3})?$", re.IGNORECASE
)


def _has_cjk(text):
    return bool(re.search(f"[{CJK}]", text))


def _phrase_regex(phrase):
    """Whole-phrase, case-insensitive match that tolerates odd whitespace."""
    tokens = [re.escape(token) for token in phrase.split()]
    if not tokens:
        return None
    body = r"[\s ]+".join(tokens)
    if _has_cjk(phrase):
        return re.compile(body)
    return re.compile(rf"(?<![A-Za-z0-9]){body}(?![A-Za-z0-9])", re.IGNORECASE)


MAX_NAME_TOKENS = 6
MAX_NAME_LENGTH = 80


def name_is_usable(name):
    """Whether a name is short enough to turn into a matching pattern.

    The pattern allows an optional middle initial between parts, so its cost
    doubles with every extra part. A real name has a handful; a "name" of
    forty single letters (which a contestant could put in a file's properties)
    would never finish matching.
    """
    name = " ".join((name or "").replace(",", " ").split())
    return bool(name) and len(name) <= MAX_NAME_LENGTH and len(name.split()) <= MAX_NAME_TOKENS


def name_variants(name):
    """Orderings in which a full name plausibly appears in a document."""
    name = " ".join(name.replace(",", " ").split())
    tokens = name.split()
    if not tokens or not name_is_usable(name):
        return []
    if len(tokens) == 1:
        # A single CJK token is a complete Chinese name; a single Latin word
        # is too ambiguous to redact automatically.
        return [name] if _has_cjk(name) and len(name) >= 2 else []
    first, last = tokens[0], tokens[-1]
    variants = {
        name,
        f"{first} {last}",
        f"{last} {first}",
        f"{last} {' '.join(tokens[:-1])}",
        f"{' '.join(tokens[1:])} {first}",
    }
    return sorted(variants, key=len, reverse=True)


def _name_regexes(name):
    regexes = []
    for variant in name_variants(name):
        tokens = [re.escape(token) for token in variant.split()]
        if len(tokens) == 1:
            regexes.append(re.compile(tokens[0]))
            continue
        # Allow a comma or a middle initial between the parts.
        joiner = r"(?:,?[\s ]+(?:[A-Z]\.?[\s ]+)?)"
        body = joiner.join(tokens)
        regexes.append(re.compile(rf"(?<![A-Za-z]){body}(?![A-Za-z])", re.IGNORECASE))
    return regexes


def name_parts(name):
    """Individual name tokens worth flagging when they appear alone."""
    parts = []
    for token in re.split(r"[\s,]+", name or ""):
        token = token.strip(".")
        if len(token) >= 2 and token.lower() not in {p.lower() for p in parts}:
            parts.append(token)
    return parts


def school_parts(school):
    parts = []
    for token in re.split(r"[\s,.'’()\-]+", school or ""):
        if len(token) >= 3 and token.lower() not in SCHOOL_STOPWORDS and not token.isdigit():
            parts.append(token)
    return parts


def _part_regex(token):
    if _has_cjk(token):
        return re.compile(re.escape(token))
    # Case-sensitive on purpose: "Long" the surname, not "long" the adjective.
    return re.compile(rf"(?<![A-Za-z]){re.escape(token)}(?![A-Za-z])")


_IN_REFERENCE = re.compile(r"://|www\.|doi|/|isbn|issn", re.IGNORECASE)


def phone_spans(text):
    """Phone numbers, but never digits that sit inside a link.

    Web addresses and DOIs are full of long numbers ("…/c_13912345678.htm");
    blacking them out would destroy the very citation a judge needs to check.
    """
    spans = []
    for match in PHONE_RE.finditer(text):
        start = max(
            text.rfind(" ", 0, match.start()) + 1,
            text.rfind("\n", 0, match.start()) + 1,
            match.start() - 300,
        )
        end = match.end()
        while end < len(text) and end - match.end() < 300 and not text[end].isspace():
            end += 1
        if not _IN_REFERENCE.search(text[start:end]):
            spans.append((match.start(), match.end()))
    return spans


def is_identity_line(line):
    """A labelled line such as "Name: Jane Doe" or a byline such as "By Jane Doe"."""
    line = line.strip()
    return len(line) <= MAX_LABEL_LINE and bool(LABEL_LINE_RE.match(line) or BYLINE_RE.match(line))


def is_page_number(line):
    line = line.strip()
    return len(line) <= 30 and bool(PAGE_NUMBER_RE.match(line))


def find_spans(text, *, author_name="", author_school="", meta_authors=()):
    """Identifying spans in one page of text.

    Returns dicts with start, end, kind, on (redact outright, or only suggest)
    and t (the term, for suggestions).
    """
    found = []

    def add(start, end, kind, on, term=""):
        if end > start:
            found.append({"start": start, "end": end, "kind": kind, "on": on, "t": term})

    for match in EMAIL_RE.finditer(text):
        add(match.start(), match.end(), "email", True)
    for start, end in phone_spans(text):
        add(start, end, "phone", True)
    if author_name:
        for regex in _name_regexes(author_name):
            for match in regex.finditer(text):
                add(match.start(), match.end(), "name", True)
    for meta_author in meta_authors:
        if author_name and meta_author.lower() == author_name.lower():
            continue
        for regex in _name_regexes(meta_author):
            for match in regex.finditer(text):
                add(match.start(), match.end(), "meta_name", True, meta_author)
    if author_school:
        regex = _phrase_regex(author_school)
        if regex:
            for match in regex.finditer(text):
                add(match.start(), match.end(), "school", True)

    seen = set()
    for kind, tokens in (
        ("name_part", name_parts(author_name)),
        ("name_part", [t for m in meta_authors for t in name_parts(m)]),
        ("school_part", school_parts(author_school)),
    ):
        for token in tokens:
            if token.lower() in seen:
                continue
            seen.add(token.lower())
            for match in _part_regex(token).finditer(text):
                add(match.start(), match.end(), kind, False, token)
    for match in SELF_REFERENCE_RE.finditer(text):
        add(match.start(), match.end(), "self", False)
    return found


def has_acknowledgements(text):
    return bool(ACKNOWLEDGEMENT_RE.search(text))


def hard_leaks(text, author_name="", author_email="", author_school=""):
    """Identifiers that must not be released without an explicit override."""
    leaks = []
    if author_name and any(regex.search(text) for regex in _name_regexes(author_name)):
        leaks.append("name")
    if author_email and author_email.lower() in text.lower():
        leaks.append("email")
    elif EMAIL_RE.search(text):
        leaks.append("any_email")
    if author_school:
        regex = _phrase_regex(author_school)
        if regex and regex.search(text):
            leaks.append("school")
    return leaks
