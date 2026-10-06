"""Working with submitted PDFs: rendering, stored layouts, released pages.

Three directories under MEDIA_ROOT, none of them served by the web server:

    originals/<random>.pdf       the file as submitted            (admins only)
    work/<random>/               unredacted page images + layout  (admins only)
    released/<random>/           page images with redactions burned in (judges)
"""

import gzip
import json
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

from django.conf import settings

PDF_MAGIC = b"%PDF-"
BOX_PADDING_PX = 2


class PdfError(Exception):
    """The file could not be turned into pages. str() is a stable code."""


def looks_like_pdf(head):
    return PDF_MAGIC in head[:1024]


def new_dir(kind):
    """Create and return (token, path) for a fresh work or released directory."""
    token = secrets.token_hex(16)
    path = Path(settings.MEDIA_ROOT) / kind / token
    path.mkdir(parents=True)
    return token, path


def dir_path(kind, token):
    if not token or not all(ch in "0123456789abcdef" for ch in token):
        raise PdfError("missing")
    return Path(settings.MEDIA_ROOT) / kind / token


def remove_dir(kind, token):
    if token:
        shutil.rmtree(dir_path(kind, token), ignore_errors=True)


def render(source_path):
    """Run the worker on a stored PDF. Returns the token of the work directory."""
    token, out_dir = new_dir("work")
    command = [
        sys.executable,
        "-m",
        "portal.pdfworker",
        str(source_path),
        str(out_dir),
        str(settings.MAX_ESSAY_PAGES),
        str(settings.PDF_RENDER_DPI),
        str(settings.PDF_CPU_SECONDS),
        str(settings.PDF_MEMORY_MB),
    ]
    try:
        result = subprocess.run(  # noqa: S603 - fixed argv, no shell
            command,
            cwd=settings.BASE_DIR,
            capture_output=True,
            text=True,
            timeout=settings.PDF_TIMEOUT_SECONDS,
            env={"PATH": "/usr/local/bin:/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"},
        )
    except subprocess.TimeoutExpired as exc:
        remove_dir("work", token)
        raise PdfError("too_complex") from exc
    outcome = {}
    try:
        outcome = json.loads(result.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError):
        pass
    if result.returncode != 0 or not outcome.get("ok"):
        remove_dir("work", token)
        # Killed by a limit (no JSON) means the file was too heavy to process.
        raise PdfError(outcome.get("error") or "too_complex")
    return token


def load_layout(token):
    try:
        with gzip.open(
            dir_path("work", token) / "layout.json.gz", "rt", encoding="utf-8"
        ) as handle:
            return json.load(handle)
    except (OSError, ValueError) as exc:
        raise PdfError("missing") from exc


def work_page(token, number):
    return dir_path("work", token) / f"page-{int(number)}.png"


def released_page(token, number):
    return dir_path("released", token) / f"page-{int(number)}.png"


def render_release(work_token, page_count, redactions, dropped):
    """Burn the applied redactions into copies of the kept pages.

    Returns (token, number_of_pages). The copies are plain images: no text
    layer, no metadata, nothing underneath a black box.
    """
    from PIL import Image, ImageDraw

    token, out_dir = new_dir("released")
    by_page = {}
    for box in redactions:
        if box.get("on"):
            by_page.setdefault(box["p"], []).append(box)
    kept = 0
    for index in range(page_count):
        if index in dropped:
            continue
        kept += 1
        with Image.open(work_page(work_token, index + 1)) as image:
            image.load()
            width, height = image.size
            draw = ImageDraw.Draw(image)
            fill = 0 if image.mode == "L" else (0, 0, 0)
            for box in by_page.get(index, []):
                draw.rectangle(
                    [
                        box["x"] * width - BOX_PADDING_PX,
                        box["y"] * height - BOX_PADDING_PX,
                        (box["x"] + box["w"]) * width + BOX_PADDING_PX,
                        (box["y"] + box["h"]) * height + BOX_PADDING_PX,
                    ],
                    fill=fill,
                )
            image.save(out_dir / f"page-{kept}.png", "PNG", optimize=True)
    return token, kept
