"""A tiny PDF writer for demo data and tests.

Produces plain, valid PDFs set in Courier (whose fixed width makes line
breaking exact without font metrics): a running header, an optional title
page, body paragraphs, superscript note marks with footnotes at the foot of
the page, and a bibliography. Not used by the portal itself.
"""

import textwrap

PAGE_W, PAGE_H = 612, 792
LEFT, RIGHT = 72, 540
BODY_SIZE, NOTE_SIZE, MARK_SIZE = 11, 8, 7
CHAR_W = 0.6  # Courier advance, in ems
BODY_TOP, BODY_LEADING, LINES_PER_PAGE = 708, 18, 30
NOTES_TOP, NOTE_LEADING = 132, 10
WRAP = int((RIGHT - LEFT) / (BODY_SIZE * CHAR_W))
NOTE_WRAP = int((RIGHT - LEFT) / (NOTE_SIZE * CHAR_W))


def _hex(text):
    return "<" + text.encode("cp1252", "replace").hex() + ">"


def _show(x, y, size, text):
    return f"BT /F1 {size} Tf {x:.2f} {y:.2f} Td {_hex(text)} Tj ET"


def _assemble(page_streams, author=None):
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        None,
        "<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>",
    ]
    kids = []
    for stream in page_streams:
        page_id, content_id = len(objects) + 1, len(objects) + 2
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_W} {PAGE_H}] "
            f"/Contents {content_id} 0 R /Resources << /Font << /F1 3 0 R >> >> >>"
        )
        objects.append(f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream")
        kids.append(f"{page_id} 0 R")
    objects[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>"
    info_id = None
    if author:
        objects.append(f"<< /Author {_hex(author)} /Producer {_hex('demo_pdf')} >>")
        info_id = len(objects)

    out = b"%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n{body}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    trailer = f"/Size {len(objects) + 1} /Root 1 0 R"
    if info_id:
        trailer += f" /Info {info_id} 0 R"
    out += f"trailer\n<< {trailer} >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


def simple_pdf(pages, author=None):
    """One list of text lines per page, top to bottom."""
    streams = []
    for lines in pages:
        ops = [
            _show(LEFT, BODY_TOP + 36 - index * 14, BODY_SIZE, line)
            for index, line in enumerate(lines)
        ]
        streams.append("\n".join(ops))
    return _assemble(streams, author)


def essay_pdf(
    paragraphs,
    *,
    title_page=None,
    header=None,
    footnotes=None,
    bibliography=None,
    author=None,
):
    """A formatted essay.

    footnotes maps a paragraph index to the note attached to its last word;
    header is the running head (a page number is appended); title_page is a
    list of lines for a separate cover page.
    """
    footnotes = footnotes or {}
    rows = []  # (text, note_number or None)
    numbered = {}
    for index, paragraph in enumerate(paragraphs):
        wrapped = textwrap.wrap(paragraph, WRAP, initial_indent="    ") or [""]
        for position, line in enumerate(wrapped):
            mark = None
            if index in footnotes and position == len(wrapped) - 1:
                mark = len(numbered) + 1
                numbered[mark] = footnotes[index]
            rows.append((line, mark))
        rows.append(("", None))
    if bibliography:
        rows.append(("Works Cited", None))
        rows.append(("", None))
        for entry in bibliography:
            for line in textwrap.wrap(entry, WRAP, subsequent_indent="    "):
                rows.append((line, None))

    streams = []
    if title_page:
        ops = [
            _show(LEFT + 60, 520 - index * 26, BODY_SIZE + (3 if index == 0 else 0), line)
            for index, line in enumerate(title_page)
        ]
        streams.append("\n".join(ops))

    first_body_page = len(streams) + 1
    for start in range(0, len(rows), LINES_PER_PAGE):
        chunk = rows[start : start + LINES_PER_PAGE]
        number = len(streams) + 2 - first_body_page
        ops, notes = [], []
        if header:
            label = f"{header} {number}"
            ops.append(_show(RIGHT - len(label) * BODY_SIZE * CHAR_W, 750, BODY_SIZE, label))
        else:
            ops.append(_show((LEFT + RIGHT) / 2, 40, BODY_SIZE, str(number)))
        for position, (line, mark) in enumerate(chunk):
            y = BODY_TOP - position * BODY_LEADING
            if line:
                ops.append(_show(LEFT, y, BODY_SIZE, line))
            if mark:
                x = LEFT + len(line) * BODY_SIZE * CHAR_W
                ops.append(_show(x, y + 4, MARK_SIZE, str(mark)))
                notes.append(mark)
        if notes:
            ops.append(f"{LEFT} {NOTES_TOP + 10} m {LEFT + 140} {NOTES_TOP + 10} l 0.5 w S")
            y = NOTES_TOP
            for mark in notes:
                wrapped = textwrap.wrap(numbered[mark], NOTE_WRAP - 4)
                ops.append(_show(LEFT, y + 3, MARK_SIZE - 1, str(mark)))
                for line in wrapped:
                    ops.append(_show(LEFT + 12, y, NOTE_SIZE, line))
                    y -= NOTE_LEADING
        streams.append("\n".join(ops))
    return _assemble(streams, author)
