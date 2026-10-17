"""OCR performed in the user's browser (Tesseract.js) for pages the server
could not read itself.

Flow: the browser fetches a page image from ``ocr_page_image`` (whose pixel
size is recorded), recognises it, and posts the words back. The words are
validated (page must be pending, image size must match, boxes inside the
image, bounded counts) and converted to page coordinates. They are then
treated exactly like server OCR output: rule detection runs on them and,
for scanned PDF pages, redaction rasterises the page.

The boxes come from the user's own browser, so a tampered client can only
affect the redaction of its own document.
"""

from __future__ import annotations

import io

import pymupdf
from PIL import Image
from pydantic import BaseModel, Field

from app.config import settings
from app.errors import SherlockError
from app.services.scanner import MAX_FINDINGS, add_rule_findings
from app.services.sessions import PageInfo, Session
from app.services.text_extraction import PageText, Word, render_page

MAX_OCR_IMAGE_SIDE = 5000
MAX_WORDS_TOTAL = 20_000


class OCRWord(BaseModel):
    text: str = Field(min_length=1, max_length=100)
    x0: float
    y0: float
    x1: float
    y1: float
    line: int = Field(ge=0, le=100_000)


class OCRPage(BaseModel):
    page: int = Field(ge=1)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    words: list[OCRWord] = Field(max_length=MAX_WORDS_TOTAL)


class OCRSubmission(BaseModel):
    pages: list[OCRPage] = Field(min_length=1, max_length=100)


def ocr_page_image(session: Session, page_number: int) -> bytes:
    """PNG of a pending page for the browser to OCR. Records its pixel size."""
    index = page_number - 1
    if not 0 <= index < len(session.pages):
        raise SherlockError("page_not_found", "That page does not exist.", 404)
    if session.pages[index].source != "pending":
        raise SherlockError("ocr_not_needed", "This page does not need OCR.", 409)

    if session.kind == "pdf":
        doc = pymupdf.open(session.work_path)
        try:
            image = render_page(doc[index], settings.client_ocr_dpi)
        finally:
            doc.close()
    else:
        with Image.open(session.work_path) as source:
            source.load()
            image = source.convert("RGB")
        if max(image.size) > MAX_OCR_IMAGE_SIDE:
            image.thumbnail((MAX_OCR_IMAGE_SIDE, MAX_OCR_IMAGE_SIDE))

    with session.lock:
        session.ocr_images[index] = image.size
    buf = io.BytesIO()
    image.save(buf, "PNG")
    return buf.getvalue()


def apply_client_ocr(session: Session, submission: OCRSubmission) -> None:
    if sum(len(p.words) for p in submission.pages) > MAX_WORDS_TOTAL:
        raise SherlockError("ocr_too_large", "Too much OCR text was submitted.", 413)

    with session.lock:
        prepared: list[tuple[int, PageText]] = []
        for page in submission.pages:
            index = page.page - 1
            if not 0 <= index < len(session.pages) or session.pages[index].source != "pending":
                raise SherlockError("invalid_ocr", "OCR results do not match a page awaiting OCR.", 409)
            if session.ocr_images.get(index) != (page.width, page.height):
                raise SherlockError("invalid_ocr", "OCR results do not match the page image.", 409)

            info = session.pages[index]
            sx, sy = info.width / page.width, info.height / page.height
            words: list[Word] = []
            for w in page.words:
                x0, x1 = sorted((max(0.0, min(w.x0, page.width)), max(0.0, min(w.x1, page.width))))
                y0, y1 = sorted((max(0.0, min(w.y0, page.height)), max(0.0, min(w.y1, page.height))))
                text = w.text.strip()
                if not text or x1 - x0 < 1 or y1 - y0 < 1:
                    continue
                words.append(Word(text, (x0 * sx, y0 * sy, x1 * sx, y1 * sy), (w.line,)))
            prepared.append((index, PageText(index, info.width, info.height, "ocr", words).build()))

        for index, page_text in prepared:
            info = session.pages[index]
            session.pages[index] = PageInfo(info.index, info.width, info.height, "ocr")
            session.page_texts[index] = page_text
            if not add_rule_findings(session, page_text):
                session.warnings.append(f"Only the first {MAX_FINDINGS} findings are shown.")
                break
