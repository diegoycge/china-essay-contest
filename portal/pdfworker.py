"""Render a PDF's pages to images and record where every word sits.

Run as a separate, short-lived process (see services/pdf.py):

    python -m portal.pdfworker <input.pdf> <output_dir> <max_pages> <dpi> <cpu_s> <memory_mb>

Submissions come from contestants and are parsed here by PDFium, a native
library. Keeping that in its own process, under CPU, memory and time limits,
means a malformed or malicious file can at worst kill this process; it cannot
stall or crash the web server. This module must not import Django.

Output: page-1.png … page-N.png and layout.json.gz in the output directory,
and one line of JSON on stdout ({"ok": true} or {"error": "<code>"}).
"""

import ctypes
import gzip
import json
import os
import sys

MAX_LONG_SIDE_PX = 2400  # whatever the page size, no bitmap is larger than this
MAX_TOKENS_PER_PAGE = 30_000
MAX_TOTAL_CHARS = 600_000  # roughly 100,000 words
CJK_RANGES = ((0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF), (0x3040, 0x30FF))


class Failure(Exception):
    pass


def _is_cjk(code):
    return any(low <= code <= high for low, high in CJK_RANGES)


def _tokens(pdfium_c, page, textpage, width, height):
    """Words (or single CJK characters) with boxes as fractions of the page.

    Each token is [text, x0, y0, x1, y1, separator, line]; the separator is
    what follows it in reading order ("", " " or "\\n").
    """
    raw_page, raw_text = page.raw, textpage.raw
    count = textpage.count_chars()
    dx, dy = ctypes.c_int(), ctypes.c_int()

    def device(x, y):
        pdfium_c.FPDF_PageToDevice(
            raw_page, 0, 0, width, height, 0, x, y, ctypes.byref(dx), ctypes.byref(dy)
        )
        return dx.value, dy.value

    tokens, line = [], 0
    current = None  # [chars, left, bottom, right, top] in page space

    def finish(separator):
        nonlocal current
        if current is not None:
            chars, left, bottom, right, top = current
            ax, ay = device(left, top)
            bx, by = device(right, bottom)
            x0, x1 = sorted((ax / width, bx / width))
            y0, y1 = sorted((ay / height, by / height))
            box = [round(min(max(v, 0.0), 1.0), 4) for v in (x0, y0, x1, y1)]
            tokens.append(["".join(chars), *box, separator, line])
            current = None
        elif tokens and separator and not tokens[-1][5]:
            tokens[-1][5] = separator
        elif tokens and separator == "\n":
            tokens[-1][5] = "\n"

    for index in range(count):
        code = pdfium_c.FPDFText_GetUnicode(raw_text, index)
        if code in (10, 13):
            finish("\n")
            if tokens and tokens[-1][6] == line:
                line += 1
            continue
        if code in (0, 0xFFFE, 0xFFFF) or code == 32 or code == 0xA0 or code == 9:
            finish(" ")
            continue
        if code == 2:  # PDFium's marker for a word hyphenated across lines
            code = 0x2D
        char = "�" if 0xD800 <= code <= 0xDFFF or code > 0x10FFFF else chr(code)
        if char.isspace():
            finish(" ")
            continue
        left, bottom, right, top = textpage.get_charbox(index, loose=True)
        if right <= left or top <= bottom:
            continue
        if _is_cjk(code):
            finish("")
            current = [[char], left, bottom, right, top]
            finish("")
            continue
        if current is not None:
            # A jump down the page without a newline character: start a new line.
            mid = (bottom + top) / 2
            if not (current[2] - (current[4] - current[2]) <= mid <= current[4] + (top - bottom)):
                finish("\n")
                line += 1
        if current is None:
            current = [[char], left, bottom, right, top]
        else:
            current[0].append(char)
            current[1] = min(current[1], left)
            current[2] = min(current[2], bottom)
            current[3] = max(current[3], right)
            current[4] = max(current[4], top)
        if len(tokens) > MAX_TOKENS_PER_PAGE:
            raise Failure("too_much_text")
    finish("\n")
    return tokens


def _save_png(image, path):
    # Text pages are grey; storing them as such halves the file size.
    from PIL import ImageChops

    grey = image.convert("L")
    if ImageChops.difference(image, grey.convert("RGB")).getbbox() is None:
        image = grey
    image.save(path, "PNG", optimize=True)


def process(source, out_dir, max_pages, dpi):
    import pypdfium2 as pdfium
    import pypdfium2.raw as pdfium_c

    try:
        pdf = pdfium.PdfDocument(source)
    except pdfium.PdfiumError as exc:
        raise Failure("password" if "password" in str(exc).lower() else "unreadable") from exc
    count = len(pdf)
    if count == 0:
        raise Failure("unreadable")
    if count > max_pages:
        raise Failure("too_many_pages")

    try:
        author = (pdf.get_metadata_dict() or {}).get("Author", "") or ""
    except Exception:  # metadata is optional and sometimes garbage
        author = ""

    pages, total_chars = [], 0
    for index in range(count):
        page = pdf[index]
        width_pt, height_pt = page.get_size()
        if width_pt < 1 or height_pt < 1:
            raise Failure("unreadable")
        scale = min(dpi / 72, MAX_LONG_SIDE_PX / max(width_pt, height_pt))
        # Annotations and form fields are not drawn: comments and stamps can
        # carry names, and they are not part of the essay.
        bitmap = page.render(scale=scale, may_draw_forms=False, draw_annots=False)
        image = bitmap.to_pil().convert("RGB")
        width, height = image.size
        _save_png(image, os.path.join(out_dir, f"page-{index + 1}.png"))

        textpage = page.get_textpage()
        tokens = _tokens(pdfium_c, page, textpage, width, height)
        total_chars += sum(len(token[0]) + 1 for token in tokens)
        if total_chars > MAX_TOTAL_CHARS:
            raise Failure("too_much_text")
        pages.append({"w": round(width_pt, 1), "h": round(height_pt, 1), "tokens": tokens})
        textpage.close()
        bitmap.close()
        page.close()

    layout = {"version": 1, "authors": [author[:200]] if author.strip() else [], "pages": pages}
    with gzip.open(os.path.join(out_dir, "layout.json.gz"), "wt", encoding="utf-8") as handle:
        json.dump(layout, handle, ensure_ascii=False, separators=(",", ":"))


def limit_resources(cpu_seconds, memory_mb):
    """Cap this process before it touches the file.

    Done here rather than by the parent at fork time, which is not safe in a
    process that has other threads.
    """
    import resource

    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
    try:
        memory = memory_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
    except (ValueError, OSError):  # not enforceable on macOS; Linux is what we deploy on
        pass
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def main(argv):
    source, out_dir, max_pages, dpi = argv[1], argv[2], int(argv[3]), int(argv[4])
    limit_resources(int(argv[5]), int(argv[6]))
    try:
        process(source, out_dir, max_pages, dpi)
    except Failure as failure:
        print(json.dumps({"error": str(failure)}))
        return 2
    except MemoryError:
        print(json.dumps({"error": "too_complex"}))
        return 2
    except Exception as exc:  # anything PDFium or Pillow throws on a hostile file
        print(json.dumps({"error": "unreadable", "detail": type(exc).__name__}))
        return 2
    print(json.dumps({"ok": True}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
