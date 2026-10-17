"""Real redaction: content is removed, never just covered.

PDF pages with a text layer
    PyMuPDF redaction annotations are applied with ``apply_redactions``, which
    deletes the underlying characters from the page content stream and blanks
    image pixels under each box. Links touching a redacted area are removed.

Scanned PDF pages (findings came from OCR)
    The page is rendered to pixels, the boxes are painted black in the raster,
    and the page is replaced by that single image. No original image or hidden
    text layer survives on that page.

Images
    Pixels inside each box are overwritten in a new image, exported as PNG
    with no metadata.

Every output is re-opened and checked before it is offered for download. If
any check fails the output is deleted and an error is returned instead.
"""

from __future__ import annotations

import io
import logging
import math
import secrets
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw

from app.config import settings
from app.errors import SherlockError
from app.services.detection import normalise
from app.services.sessions import Finding, Output, Session, store
from app.services.text_extraction import Rect, render_page

log = logging.getLogger("sherlock.redaction")

PDF_PAD = 1.0  # points
IMAGE_PAD = 3  # pixels
BLACK = (0, 0, 0)


class VerificationError(Exception):
    pass


def select_findings(session: Session, finding_ids: list[str]) -> list[Finding]:
    """Validate client-sent IDs against the server-side scan results."""
    if not finding_ids:
        raise SherlockError("nothing_selected", "Select at least one finding to redact.")
    unique = list(dict.fromkeys(finding_ids))
    unknown = [fid for fid in unique if fid not in session.findings]
    if unknown:
        raise SherlockError(
            "invalid_selection", "The selection does not match this scan. Scan the file again."
        )
    selected = [session.findings[fid] for fid in unique]
    if any(not f.locatable for f in selected):
        raise SherlockError(
            "unlocatable_finding",
            "One or more selected findings could not be located on the page, so they cannot be "
            "redacted automatically. Deselect them and remove that information manually.",
            422,
        )
    return selected


def redact(session: Session, finding_ids: list[str]) -> Output:
    selected = select_findings(session, finding_ids)
    token = secrets.token_urlsafe(32)
    if session.kind == "pdf":
        suffix, media_type = ".pdf", "application/pdf"
    elif session.upload.format == "jpeg":
        suffix, media_type = ".jpg", "image/jpeg"
    else:
        suffix, media_type = ".png", "image/png"
    out_path = session.workdir / f"output-{secrets.token_hex(8)}{suffix}"

    try:
        if session.kind == "pdf":
            page_count = _redact_pdf(session, selected, out_path)
            _verify_pdf(session, selected, out_path)
        else:
            page_count = 1
            _redact_image(session, selected, out_path)
            _verify_image(selected, out_path)
    except VerificationError as exc:
        out_path.unlink(missing_ok=True)
        log.error("redaction verification failed: %s", exc)
        raise SherlockError(
            "redaction_verification_failed",
            "Sherlock could not confirm that every selected item was removed, so no file was "
            "produced. Nothing unsafe was offered for download.",
            500,
        ) from exc
    except SherlockError:
        out_path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        out_path.unlink(missing_ok=True)
        log.exception("redaction failed")
        raise SherlockError("redaction_failed", "Redaction failed. No output was produced.", 500) from exc

    output = Output(
        token=token,
        path=out_path,
        filename=f"{session.upload.display_stem}-sherlock-redacted{suffix}",
        media_type=media_type,
        page_count=page_count,
    )
    store.set_output(session, output)
    log.info("redaction complete: kind=%s items=%d", session.kind, len(selected))
    return output


# --------------------------------------------------------------------------
# PDF
# --------------------------------------------------------------------------

def _pad(rect: Rect, pad: float) -> pymupdf.Rect:
    return pymupdf.Rect(rect[0] - pad, rect[1] - pad, rect[2] + pad, rect[3] + pad)


def _group_by_page(selected: list[Finding]) -> dict[int, list[Finding]]:
    grouped: dict[int, list[Finding]] = {}
    for f in selected:
        grouped.setdefault(f.page_index, []).append(f)
    return grouped


def _raster_page_png(page: pymupdf.Page, rects: list[pymupdf.Rect]) -> bytes:
    dpi = settings.raster_output_dpi
    scale = dpi / 72.0
    image = render_page(page, dpi)
    draw = ImageDraw.Draw(image)
    for r in rects:
        draw.rectangle(
            [
                max(0, math.floor(r.x0 * scale) - IMAGE_PAD),
                max(0, math.floor(r.y0 * scale) - IMAGE_PAD),
                min(image.width - 1, math.ceil(r.x1 * scale) + IMAGE_PAD),
                min(image.height - 1, math.ceil(r.y1 * scale) + IMAGE_PAD),
            ],
            fill=BLACK,
        )
    buf = io.BytesIO()
    image.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def _redact_pdf(session: Session, selected: list[Finding], out_path: Path) -> int:
    by_page = _group_by_page(selected)
    raster_pages = {i for i in by_page if session.pages[i].source == "ocr"}

    src = pymupdf.open(session.work_path)
    out = pymupdf.open()
    try:
        for index, findings in by_page.items():
            if index in raster_pages:
                continue
            page = src[index]
            rects = [_pad(r, PDF_PAD) for f in findings for r in f.rects]
            for r in rects:
                page.add_redact_annot(r, fill=BLACK, cross_out=False)
            for link in page.get_links():
                if any(pymupdf.Rect(link["from"]).intersects(r) for r in rects):
                    page.delete_link(link)
            page.apply_redactions(
                images=pymupdf.PDF_REDACT_IMAGE_PIXELS,
                graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED,
                text=pymupdf.PDF_REDACT_TEXT_REMOVE,
            )

        # Comments and other markup annotations are not scanned, so they are
        # removed rather than risk carrying sensitive text into the output.
        for page in src:
            for annot in list(page.annots()):
                page.delete_annot(annot)

        # Build a fresh document: this drops document-level metadata, XMP,
        # bookmarks, embedded files and document JavaScript from the source.
        for page in src:
            if page.number in raster_pages:
                rects = [_pad(r, 0) for f in by_page[page.number] for r in f.rects]
                png = _raster_page_png(page, rects)
                new_page = out.new_page(width=page.rect.width, height=page.rect.height)
                new_page.insert_image(new_page.rect, stream=png)
            else:
                out.insert_pdf(src, from_page=page.number, to_page=page.number)

        out.set_metadata({})
        out.del_xml_metadata()
        out.scrub(
            attached_files=True,
            clean_pages=False,
            embedded_files=True,
            hidden_text=False,
            javascript=True,
            metadata=True,
            redactions=False,
            remove_links=False,
            reset_fields=False,
            reset_responses=False,
            thumbnails=True,
            xml_metadata=True,
        )
        out.save(out_path, garbage=4, deflate=True, clean=True)
        return out.page_count
    finally:
        out.close()
        src.close()


def _verify_pdf(session: Session, selected: list[Finding], out_path: Path) -> None:
    """Re-open the output and prove the selected text is gone.

    For each selected value, the number of times it can still be extracted
    from the page must have dropped by at least the number of occurrences
    selected. This tolerates the same text remaining elsewhere (unselected,
    or inside a longer word) while catching any selected occurrence that
    survived. Text inside every redaction box must also be empty of it.
    """
    selected_ids = {f.id for f in selected}
    unselected = [f for f in session.findings.values() if f.id not in selected_ids]
    by_page = _group_by_page(selected)

    before_doc = pymupdf.open(session.work_path)
    doc = pymupdf.open(out_path)
    try:
        if doc.page_count != len(session.pages):
            raise VerificationError("page count changed")
        if any(v for k, v in doc.metadata.items() if k not in ("format", "encryption") and v):
            raise VerificationError("metadata not removed")
        if any(page.first_annot is not None for page in doc):
            raise VerificationError("annotations not removed")

        all_uris = [(link.get("uri") or "").lower() for page in doc for link in page.get_links()]

        for index, findings in by_page.items():
            page = doc[index]
            after_text = normalise(page.get_text("text"))

            if session.pages[index].source == "ocr":
                if after_text:
                    raise VerificationError("rasterised page still has a text layer")
                if len(page.get_images()) != 1:
                    raise VerificationError("rasterised page has unexpected images")
                for f in findings:
                    _verify_dark(page, f.rects)
                continue

            before_text = normalise(before_doc[index].get_text("text"))
            values = {normalise(f.value) for f in findings}
            for value in values:
                chosen = sum(1 for f in findings if normalise(f.value) == value)
                if after_text.count(value) > max(0, before_text.count(value) - chosen):
                    raise VerificationError("a selected occurrence is still extractable")

            redacted_rects = [_pad(r, PDF_PAD) for f in findings for r in f.rects]
            for f in findings:
                value = normalise(f.value)
                for r in f.rects:
                    if value in normalise(page.get_text("text", clip=pymupdf.Rect(r))):
                        raise VerificationError("text still extractable inside a redacted box")
            for link in page.get_links():
                if any(pymupdf.Rect(link["from"]).intersects(r) for r in redacted_rects):
                    raise VerificationError("a link over a redacted area remains")

        for f in selected:
            if f.category != "url":
                continue
            value = f.value.lower().replace(" ", "")
            kept = any(normalise(u.value) == normalise(f.value) for u in unselected)
            if not kept and any(value in uri.replace(" ", "") for uri in all_uris):
                raise VerificationError("value still present in a link")
    finally:
        doc.close()
        before_doc.close()


def _verify_dark(page: pymupdf.Page, rects: list[Rect]) -> None:
    """Check a rasterised page really is black inside each box."""
    dpi = 72
    image = render_page(page, dpi).convert("L")
    for r in rects:
        # Sample the inner area to avoid anti-aliased edges.
        box = (
            math.ceil(r[0]) + 1, math.ceil(r[1]) + 1,
            max(math.ceil(r[0]) + 2, math.floor(r[2]) - 1),
            max(math.ceil(r[1]) + 2, math.floor(r[3]) - 1),
        )
        lo, hi = image.crop(box).getextrema()
        if hi > 40:
            raise VerificationError("rasterised box is not fully dark")


# --------------------------------------------------------------------------
# Images
# --------------------------------------------------------------------------

def _image_boxes(selected: list[Finding], width: int, height: int) -> list[tuple[int, int, int, int]]:
    boxes = []
    for f in selected:
        for r in f.rects:
            boxes.append(
                (
                    max(0, math.floor(r[0]) - IMAGE_PAD),
                    max(0, math.floor(r[1]) - IMAGE_PAD),
                    min(width - 1, math.ceil(r[2]) + IMAGE_PAD),
                    min(height - 1, math.ceil(r[3]) + IMAGE_PAD),
                )
            )
    return boxes


def _redact_image(session: Session, selected: list[Finding], out_path: Path) -> None:
    with Image.open(session.work_path) as source:
        source.load()
        image = source.copy()
    fill = (0, 0, 0, 255) if image.mode == "RGBA" else BLACK
    draw = ImageDraw.Draw(image)
    for box in _image_boxes(selected, image.width, image.height):
        draw.rectangle(box, fill=fill)
    image.info = {}  # drop EXIF, ICC, XMP and text chunks
    if out_path.suffix == ".jpg":
        image.convert("RGB").save(out_path, "JPEG", quality=95, subsampling=0)
    else:
        image.save(out_path, "PNG", optimize=True)


def _verify_image(selected: list[Finding], out_path: Path) -> None:
    with Image.open(out_path) as image:
        image.load()
        if any(k in image.info for k in ("exif", "xmp", "XML:com.adobe.xmp", "icc_profile")):
            raise VerificationError("image metadata not removed")
        if getattr(image, "text", None):
            raise VerificationError("image text chunks not removed")
        rgb = image.convert("RGB")
        lossy = image.format == "JPEG"
        for box in _image_boxes(selected, image.width, image.height):
            if lossy:
                # JPEG compression adds faint ringing at block edges; check the
                # inner area is dark. The original pixels were replaced before
                # compression, so nothing of the original can come back.
                inset = 4 if min(box[2] - box[0], box[3] - box[1]) > 12 else 0
                crop = rgb.crop((box[0] + inset, box[1] + inset, box[2] + 1 - inset, box[3] + 1 - inset))
                if any(hi > 64 for _, hi in crop.getextrema()):
                    raise VerificationError("image region not fully replaced")
            else:
                crop = rgb.crop((box[0], box[1], box[2] + 1, box[3] + 1))
                if any(band != (0, 0) for band in crop.getextrema()):
                    raise VerificationError("image region not fully replaced")
