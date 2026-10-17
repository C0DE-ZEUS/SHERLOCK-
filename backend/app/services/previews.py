"""Page preview images for the review and completion screens."""

from __future__ import annotations

import io
from pathlib import Path

import pymupdf
from PIL import Image

from app.config import settings
from app.errors import SherlockError
from app.services.text_extraction import render_page

MAX_IMAGE_PREVIEW = 1600  # px on the longest side


def render_preview(path: Path, kind: str, page_index: int, page_count: int) -> bytes:
    if not 0 <= page_index < page_count:
        raise SherlockError("page_not_found", "That page does not exist.", 404)

    if kind == "pdf":
        doc = pymupdf.open(path)
        try:
            image = render_page(doc[page_index], settings.preview_dpi)
        finally:
            doc.close()
    else:
        with Image.open(path) as source:
            source.load()
            image = source.copy()
        image.thumbnail((MAX_IMAGE_PREVIEW, MAX_IMAGE_PREVIEW))

    buf = io.BytesIO()
    image.save(buf, "PNG")
    return buf.getvalue()
