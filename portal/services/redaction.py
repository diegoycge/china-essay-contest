"""Redaction boxes: where they come from and what they do to an essay.

An essay's state is three things:

  * its layout (from the PDF worker): every word on every page, with a box;
  * a list of redactions: rectangles on pages, each either applied ("on") or
    only suggested, expressed as fractions of the page so they are
    independent of image size;
  * a list of dropped pages (a title page, say).

Everything judges get is derived from those: page images with the applied
boxes burned in, and a plain-text copy with the covered words removed. There
is no separately edited text to drift out of step with the pages.
"""

import re
from collections import Counter, defaultdict

from . import anonymize as anon
from .text import count_words

TITLE_PAGE_MAX_WORDS = 120
MIN_BODY_WORDS_FOR_TITLE_PAGE = 250
EDGE_BAND = 0.09  # running heads and feet live in the top and bottom 9% of a page
REDACTED = "[REDACTED]"

# Boxes a person made (drawn, or "redact every occurrence of…") survive a
# re-run of the automatic pass; automatic ones are recomputed.
MANUAL_KINDS = ("manual", "term")
AUTO_APPLIED_KINDS = ("name", "meta_name", "school", "email", "phone", "label", "header")


# --------------------------------------------------------------------------
# Text and geometry
# --------------------------------------------------------------------------


def page_text(tokens):
    """(text, starts): the page as a string, and each token's offset in it."""
    parts, starts, offset = [], [], 0
    for token in tokens:
        starts.append(offset)
        piece = token[0] + token[5]
        parts.append(piece)
        offset += len(piece)
    return "".join(parts), starts


def _token_indices(tokens, starts, start, end):
    """Tokens that overlap text[start:end]."""
    hits = []
    for index, token in enumerate(tokens):
        token_start = starts[index]
        if token_start >= end:
            break
        if token_start + len(token[0]) > start:
            hits.append(index)
    return hits


def _boxes(tokens, indices):
    """One rectangle per line for a set of tokens: [(x, y, w, h), …]."""
    by_line = defaultdict(list)
    for index in indices:
        by_line[tokens[index][6]].append(tokens[index])
    boxes = []
    for line_tokens in by_line.values():
        x0 = min(t[1] for t in line_tokens)
        y0 = min(t[2] for t in line_tokens)
        x1 = max(t[3] for t in line_tokens)
        y1 = max(t[4] for t in line_tokens)
        boxes.append((round(x0, 4), round(y0, 4), round(x1 - x0, 4), round(y1 - y0, 4)))
    return boxes


def lines(tokens):
    """[(text, [token indices])] in reading order."""
    grouped = defaultdict(list)
    for index, token in enumerate(tokens):
        grouped[token[6]].append(index)
    return [
        (" ".join(tokens[i][0] for i in indices), indices)
        for _line, indices in sorted(grouped.items())
    ]


def _covered(token, boxes):
    cx, cy = (token[1] + token[3]) / 2, (token[2] + token[4]) / 2
    return any(
        b["x"] - 0.002 <= cx <= b["x"] + b["w"] + 0.002
        and b["y"] - 0.002 <= cy <= b["y"] + b["h"] + 0.002
        for b in boxes
    )


def _box(page, rect, kind, on, term=""):
    x, y, w, h = rect
    box = {"p": page, "x": x, "y": y, "w": w, "h": h, "kind": kind, "on": on}
    if term:
        box["t"] = term[:60]
    return box


# --------------------------------------------------------------------------
# The automatic pass
# --------------------------------------------------------------------------


def detect_title_page(layout):
    """[0] if the first page is a cover (few words, followed by the essay)."""
    pages = layout["pages"]
    if len(pages) < 2:
        return []
    first = count_words(page_text(pages[0]["tokens"])[0])
    rest = sum(count_words(page_text(page["tokens"])[0]) for page in pages[1:])
    if first <= TITLE_PAGE_MAX_WORDS and rest >= MIN_BODY_WORDS_FOR_TITLE_PAGE:
        return [0]
    return []


def _running_lines(layout, dropped):
    """Lines in the page margins that repeat from page to page.

    Returns {page: [(key, text, token indices)]}. A header such as "Zhang 3"
    is the commonest way a surname ends up on every page.
    """
    kept = [i for i in range(len(layout["pages"])) if i not in dropped]
    if len(kept) < 2:
        return {}
    candidates, pages_with = defaultdict(list), Counter()
    for index in kept:
        tokens = layout["pages"][index]["tokens"]
        keys_here = set()
        for text, indices in lines(tokens):
            centre = sum((tokens[i][2] + tokens[i][4]) / 2 for i in indices) / len(indices)
            if EDGE_BAND <= centre <= 1 - EDGE_BAND or anon.is_page_number(text) or len(text) > 90:
                continue
            key = " ".join(re.sub(r"\d+", "#", text.lower()).split())
            candidates[index].append((key, text, indices))
            keys_here.add(key)
        pages_with.update(keys_here)
    threshold = max(2, round(len(kept) * 0.6))
    return {
        index: [entry for entry in entries if pages_with[entry[0]] >= threshold]
        for index, entries in candidates.items()
    }


def auto_redactions(layout, *, author_name="", author_school="", meta_authors=(), dropped=()):
    """Boxes for everything the automatic pass can find on the kept pages."""
    dropped = set(dropped)
    name_bits = [p.lower() for p in anon.name_parts(author_name)]
    for meta_author in meta_authors:
        name_bits.extend(p.lower() for p in anon.name_parts(meta_author))
    running = _running_lines(layout, dropped)
    boxes = []
    first_kept = next((i for i in range(len(layout["pages"])) if i not in dropped), None)

    for index, page in enumerate(layout["pages"]):
        if index in dropped:
            continue
        tokens = page["tokens"]
        text, starts = page_text(tokens)
        applied = set()

        def apply(indices, kind, term="", page_index=index, page_tokens=tokens, done=applied):
            fresh = [i for i in indices if i not in done]
            if not fresh:
                return
            done.update(fresh)
            for rect in _boxes(page_tokens, fresh):
                boxes.append(_box(page_index, rect, kind, True, term))

        # Running heads: redact when they carry the author's name, or when we
        # do not know the author's name and so cannot tell.
        for _key, line_text, indices in running.get(index, []):
            lowered = line_text.lower()
            if not name_bits or any(bit in lowered for bit in name_bits):
                apply(indices, "header")
            else:
                for rect in _boxes(tokens, indices):
                    boxes.append(_box(index, rect, "header", False))
                applied.update(indices)

        if index == first_kept:
            for line_text, indices in lines(tokens)[: anon.OPENING_SCAN_LINES]:
                if anon.is_identity_line(line_text):
                    apply(indices, "label")

        spans = anon.find_spans(
            text, author_name=author_name, author_school=author_school, meta_authors=meta_authors
        )
        for span in (s for s in spans if s["on"]):
            apply(
                _token_indices(tokens, starts, span["start"], span["end"]), span["kind"], span["t"]
            )
        suggested = set()
        for span in (s for s in spans if not s["on"]):
            indices = [
                i
                for i in _token_indices(tokens, starts, span["start"], span["end"])
                if i not in applied and i not in suggested
            ]
            suggested.update(indices)
            for rect in _boxes(tokens, indices):
                boxes.append(_box(index, rect, span["kind"], False, span["t"]))
    return boxes


def term_redactions(layout, term, dropped=()):
    """Applied boxes for every occurrence of a word or phrase (a manual tool)."""
    regex = anon._phrase_regex(term)
    boxes = []
    if regex is None:
        return boxes
    for index, page in enumerate(layout["pages"]):
        if index in dropped:
            continue
        text, starts = page_text(page["tokens"])
        for match in regex.finditer(text):
            indices = _token_indices(page["tokens"], starts, match.start(), match.end())
            for rect in _boxes(page["tokens"], indices):
                boxes.append(_box(index, rect, "term", True, term))
    return boxes


def merge(old, fresh):
    """Combine a new automatic pass with what the reviewer has already done.

    Hand-made boxes are kept. Where the reviewer switched an automatic box on
    or off and the same box is found again, their choice stands.
    """

    def key(box):
        return (box["p"], box["kind"], box["x"], box["y"], box["w"], box["h"])

    choices = {key(box): box["on"] for box in old if box["kind"] not in MANUAL_KINDS}
    merged = [box for box in old if box["kind"] in MANUAL_KINDS]
    for box in fresh:
        box = dict(box)
        box["on"] = choices.get(key(box), box["on"])
        merged.append(box)
    return merged


# --------------------------------------------------------------------------
# What judges get, and what the reviewer is told
# --------------------------------------------------------------------------


def released_pages(layout, redactions, dropped):
    """The text of each kept page with every covered word removed."""
    by_page = defaultdict(list)
    for box in redactions:
        if box.get("on"):
            by_page[box["p"]].append(box)
    pages = []
    for index, page in enumerate(layout["pages"]):
        if index in dropped:
            continue
        parts, hidden = [], False
        for token in page["tokens"]:
            if _covered(token, by_page[index]):
                if not hidden:
                    parts.append(REDACTED)
                hidden = True
                if token[5] == "\n":
                    parts.append("\n")
                    hidden = False
                continue
            if hidden:
                parts.append(" ")
                hidden = False
            parts.append(token[0] + token[5])
        pages.append("".join(parts).strip())
    return pages


def summarize(redactions, dropped, text, *, author_name="", sticky=()):
    """The reviewer's checklist: what was done, and what still needs a look."""
    flags = [dict(flag) for flag in sticky]
    if dropped:
        flags.append({"kind": "pages_dropped", "items": [str(i + 1) for i in sorted(dropped)]})
    counts = Counter(box["kind"] for box in redactions if box.get("on"))
    for kind in (
        "name",
        "meta_name",
        "school",
        "email",
        "phone",
        "label",
        "header",
        "term",
        "manual",
    ):
        if counts[kind]:
            flags.append({"kind": f"redacted_{kind}", "count": counts[kind]})
    if not author_name:
        flags.append({"kind": "no_author_on_record"})
    elif not anon.name_is_usable(author_name):
        flags.append({"kind": "author_name_unusable"})
    if count_words(text) < 50:
        flags.append({"kind": "no_text_layer"})

    pending = Counter((box["kind"], box.get("t", "")) for box in redactions if not box.get("on"))
    for (kind, term), count in sorted(pending.items()):
        if kind in ("name_part", "school_part"):
            flags.append({"kind": f"{kind}_present", "term": term, "count": count})
        elif kind == "self":
            flags.append({"kind": "self_reference", "count": count})
        elif kind == "header":
            flags.append({"kind": "header_suggested", "count": count})
    if anon.has_acknowledgements(text):
        flags.append({"kind": "acknowledgements"})
    return flags


def clean(raw, page_count):
    """Validate redactions posted by the review screen. Returns a new list."""
    cleaned = []
    if not isinstance(raw, list):
        return cleaned
    for item in raw[:5000]:
        try:
            page = int(item["p"])
            x, y, w, h = (float(item[k]) for k in ("x", "y", "w", "h"))
        except (KeyError, TypeError, ValueError):
            continue
        if not 0 <= page < page_count:
            continue
        x, y = min(max(x, 0.0), 1.0), min(max(y, 0.0), 1.0)
        w, h = min(max(w, 0.0), 1.0 - x), min(max(h, 0.0), 1.0 - y)
        if w < 0.002 or h < 0.002:
            continue
        kind = str(item.get("kind", "manual"))[:20]
        on = bool(item.get("on"))
        if kind in MANUAL_KINDS and not on:
            continue  # a hand-made box that was switched off is simply deleted
        box = {"p": page, "x": round(x, 4), "y": round(y, 4), "w": round(w, 4), "h": round(h, 4)}
        box["kind"], box["on"] = kind, on
        if item.get("t"):
            box["t"] = str(item["t"])[:60]
        cleaned.append(box)
    return cleaned
