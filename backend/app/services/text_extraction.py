"""Text extraction with word positions, from PDFs (PyMuPDF) and images (Tesseract).

Every word keeps the rectangle it was found at, so detections can be mapped
back to exact regions for highlighting and redaction. Nothing here invents
coordinates: a finding is only locatable if it overlaps real word boxes.
"""

from __future__ import annotations

import io
import logging
import shutil
import warnings
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import pymupdf
from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import settings
from app.errors import SherlockError

log = logging.getLogger("sherlock.extraction")

Rect = tuple[float, float, float, float]  # x0, y0, x1, y1

Image.MAX_IMAGE_PIXELS = settings.max_image_pixels

_WINDOWS_TESSERACT_PATHS = [
    Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
    Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
]

OCR_SETUP_MESSAGE = (
    "Server-side OCR (Tesseract) is not installed, so images and scanned pages are read in "
    "your browser instead. Installing Tesseract on the server is optional (see the README)."
)


@dataclass
class Word:
    text: str
    rect: Rect
    line_key: tuple


@dataclass
class PageText:
    index: int  # 0-based
    width: float
    height: float
    source: str  # "text" | "ocr" | "pending" (needs browser OCR) | "none"
    words: list[Word] = field(default_factory=list)
    text: str = ""
    _spans: list[tuple[int, int]] = field(default_factory=list, repr=False)

    def build(self) -> "PageText":
        """Join words into searchable text, remembering each word's span."""
        parts: list[str] = []
        spans: list[tuple[int, int]] = []
        cursor = 0
        previous_line = None
        for word in self.words:
            if parts:
                sep = " " if word.line_key == previous_line else "\n"
                parts.append(sep)
                cursor += 1
            parts.append(word.text)
            spans.append((cursor, cursor + len(word.text)))
            cursor += len(word.text)
            previous_line = word.line_key
        self.text = "".join(parts)
        self._spans = spans
        return self

    def locate(self, start: int, end: int) -> list[Rect]:
        """Rectangles (one per text line) covering every word the match touches.

        Whole words are covered, so a match inside a longer word (for example
        ``Email:me@x.com``) redacts the whole word. That errs on the side of
        removing slightly more, never less.
        """
        by_line: dict[tuple, list[Rect]] = {}
        for word, (ws, we) in zip(self.words, self._spans):
            if ws < end and start < we:
                by_line.setdefault(word.line_key, []).append(word.rect)
        rects = []
        for boxes in by_line.values():
            rects.append(
                (
                    min(b[0] for b in boxes),
                    min(b[1] for b in boxes),
                    max(b[2] for b in boxes),
                    max(b[3] for b in boxes),
                )
            )
        return rects


# --------------------------------------------------------------------------
# OCR
# --------------------------------------------------------------------------

@lru_cache(maxsize=1)
def ocr_status() -> tuple[bool, str]:
    """Whether Tesseract is usable, with a human-readable explanation."""
    try:
        import pytesseract
    except ImportError:  # pragma: no cover - listed in requirements
        return False, OCR_SETUP_MESSAGE

    cmd = settings.tesseract_cmd
    if not cmd and not shutil.which("tesseract"):
        cmd = next((str(p) for p in _WINDOWS_TESSERACT_PATHS if p.exists()), None)
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd

    try:
        version = pytesseract.get_tesseract_version()
    except Exception:  # TesseractNotFoundError, OSError, ...
        return False, OCR_SETUP_MESSAGE

    try:
        available = set(pytesseract.get_languages(config=""))
    except Exception:
        available = set()
    wanted = set(settings.ocr_lang.split("+"))
    if available and not wanted <= available:
        missing = ", ".join(sorted(wanted - available))
        return False, (
            f"Tesseract {version} is installed but the OCR language data '{missing}' is missing. "
            "Install the language pack or change SHERLOCK_OCR_LANG."
        )
    return True, f"Tesseract {version} ({settings.ocr_lang})"


def ocr_words(image: Image.Image) -> list[Word]:
    """Run Tesseract and return words with pixel-space boxes."""
    import pytesseract

    try:
        data = pytesseract.image_to_data(
            image, lang=settings.ocr_lang, output_type=pytesseract.Output.DICT
        )
    except Exception as exc:
        log.warning("OCR failed: %s", type(exc).__name__)
        raise SherlockError("ocr_failed", "OCR could not read this file.", 500) from exc

    words: list[Word] = []
    for i, text in enumerate(data["text"]):
        text = (text or "").strip()
        if not text or str(data["conf"][i]) == "-1":
            continue
        left, top = float(data["left"][i]), float(data["top"][i])
        width, height = float(data["width"][i]), float(data["height"][i])
        key = (data["page_num"][i], data["block_num"][i], data["par_num"][i], data["line_num"][i])
        words.append(Word(text, (left, top, left + width, top + height), key))
    return words


# --------------------------------------------------------------------------
# PDFs
# --------------------------------------------------------------------------

def open_pdf(source: bytes | Path) -> pymupdf.Document:
    """Open a PDF from bytes (uploads) or a path (Sherlock's own working copies)."""
    try:
        if isinstance(source, bytes):
            doc = pymupdf.open(stream=source, filetype="pdf")
        else:
            doc = pymupdf.open(source)
    except Exception as exc:
        raise SherlockError("corrupt_file", "This PDF could not be opened. It may be corrupt.", 422) from exc
    if doc.needs_pass or doc.is_encrypted:
        doc.close()
        raise SherlockError(
            "password_protected",
            "This PDF is password-protected. Remove the password and upload it again.",
            422,
        )
    if not doc.is_pdf or doc.page_count == 0:
        doc.close()
        raise SherlockError("corrupt_file", "This PDF has no readable pages.", 422)
    if doc.page_count > settings.max_pdf_pages:
        count = doc.page_count
        doc.close()
        raise SherlockError(
            "too_many_pages",
            f"This PDF has {count} pages. Sherlock supports up to {settings.max_pdf_pages} pages.",
            422,
        )
    return doc


def render_page(page: pymupdf.Page, dpi: int) -> Image.Image:
    pix = page.get_pixmap(dpi=dpi, alpha=False)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def page_needs_ocr(page: pymupdf.Page, word_count: int) -> bool:
    """A page with (almost) no text layer but with images is treated as scanned."""
    return word_count < 5 and bool(page.get_images(full=False))


def extract_pdf(doc: pymupdf.Document) -> list[PageText]:
    """Pages with a text layer are read directly. Scanned pages are OCR'd on
    the server when Tesseract is available, otherwise marked "pending" so
    the browser can OCR them."""
    pages: list[PageText] = []
    ocr_ok, _ = ocr_status()

    for page in doc:
        rect = page.rect
        raw_words = page.get_text("words")
        if page_needs_ocr(page, len(raw_words)):
            if not ocr_ok:
                pages.append(PageText(page.number, rect.width, rect.height, "pending").build())
                continue
            image = render_page(page, settings.ocr_dpi)
            scale = 72.0 / settings.ocr_dpi
            words = [
                Word(w.text, tuple(c * scale for c in w.rect), w.line_key)  # type: ignore[arg-type]
                for w in ocr_words(image)
            ]
            pages.append(PageText(page.number, rect.width, rect.height, "ocr", words).build())
            continue

        words = [
            Word(w[4], (w[0], w[1], w[2], w[3]), (w[5], w[6])) for w in raw_words if w[4].strip()
        ]
        pages.append(PageText(page.number, rect.width, rect.height, "text", words).build())
    return pages


# --------------------------------------------------------------------------
# Images
# --------------------------------------------------------------------------

def load_image(data: bytes) -> Image.Image:
    """Decode an uploaded image safely and normalise orientation and mode."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            probe = Image.open(io.BytesIO(data))
            if probe.width * probe.height > settings.max_image_pixels:
                raise SherlockError("image_too_large", "This image has too many pixels to process.", 413)
            probe.verify()
            image = Image.open(io.BytesIO(data))
            image.load()
    except SherlockError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise SherlockError("image_too_large", "This image has too many pixels to process.", 413) from exc
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        raise SherlockError("corrupt_file", "This image could not be read. It may be corrupt.", 422) from exc

    # Apply EXIF rotation so boxes match what the user sees, then drop EXIF.
    image = ImageOps.exif_transpose(image)
    has_alpha = image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info)
    image = image.convert("RGBA" if has_alpha else "RGB")
    image.info = {}
    return image


def extract_image(image: Image.Image) -> PageText:
    ok, _ = ocr_status()
    if not ok:
        return PageText(0, float(image.width), float(image.height), "pending").build()
    # Tesseract reads RGB more reliably than RGBA.
    words = ocr_words(image.convert("RGB"))
    return PageText(0, float(image.width), float(image.height), "ocr", words).build()
