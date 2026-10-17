"""Scan pipeline: validate -> extract text with positions -> rule detection -> session.

AI detection (services/ai/jobs.py) and browser OCR (services/client_ocr.py)
run afterwards and add to the same session.
"""

from __future__ import annotations

import logging
import shutil

import pymupdf

from app.services import detection
from app.services.file_security import validate_upload
from app.services.sessions import Finding, PageInfo, Session, store
from app.services.text_extraction import PageText, extract_image, extract_pdf, load_image, open_pdf

log = logging.getLogger("sherlock.scan")

MAX_FINDINGS = 500


def _flatten_form_fields(doc: pymupdf.Document) -> bool:
    """Bake filled-in form fields into page content so their values are
    scanned and redacted like ordinary text. Returns True if any existed."""
    has_widgets = any(page.first_widget is not None for page in doc)
    if has_widgets:
        doc.bake(annots=False, widgets=True)
    return has_widgets


def _count_annotations(doc: pymupdf.Document) -> int:
    # page.annots() skips links and form fields.
    return sum(len(list(page.annots())) for page in doc)


def add_rule_findings(session: Session, page: PageText) -> bool:
    """Run the rule-based detectors on one page. Returns False if the
    findings cap was reached."""
    for match in detection.detect(page.text):
        if len(session.findings) >= MAX_FINDINGS:
            return False
        category = detection.CATEGORIES[match.category]
        finding_id = session.next_id("f")
        session.findings[finding_id] = Finding(
            id=finding_id,
            category=match.category,
            label=category.label,
            risk=match.risk,
            value=match.value,
            masked=detection.mask_value(match.category, match.value),
            explanation=category.explanation,
            detail=match.detail,
            page_index=page.index,
            rects=page.locate(match.start, match.end),
            source=page.source,
            span=(match.start, match.end),
        )
    return True


def scan_upload(filename: str | None, content_type: str | None, data: bytes) -> Session:
    upload = validate_upload(filename, content_type, data)
    session_id, workdir = store.create_workdir()
    try:
        warnings: list[str] = []
        if upload.is_pdf:
            work_path = workdir / "work.pdf"
            doc = open_pdf(data)
            try:
                try:
                    if _flatten_form_fields(doc):
                        warnings.append(
                            "Form fields were flattened into the page so their values could be scanned."
                        )
                except Exception:
                    warnings.append("Some form fields could not be flattened and were not scanned.")
                annotation_count = _count_annotations(doc)
                if annotation_count:
                    warnings.append(
                        f"This PDF has {annotation_count} comment(s) or annotation(s). They are not "
                        "scanned and are removed from the sanitized output."
                    )
                pages = extract_pdf(doc)
                doc.save(work_path, garbage=3, deflate=True)
            finally:
                doc.close()
        else:
            work_path = workdir / "work.png"
            image = load_image(data)
            pages = [extract_image(image)]
            image.save(work_path, "PNG")

        session = Session(
            id=session_id,
            upload=upload,
            workdir=workdir,
            work_path=work_path,
            pages=[PageInfo(p.index, p.width, p.height, p.source) for p in pages],
            warnings=warnings,
            page_texts=pages,
        )
        complete = all(add_rule_findings(session, page) for page in pages)
        if not complete:
            warnings.append(
                f"Only the first {MAX_FINDINGS} findings are shown. Split the document and scan "
                "the rest separately."
            )
        store.add(session)
        log.info(
            "scan complete: kind=%s pages=%d findings=%d pending_ocr=%d",
            session.kind, len(session.pages), len(session.findings),
            sum(p.source == "pending" for p in session.pages),
        )
        return session
    except Exception:
        shutil.rmtree(workdir, ignore_errors=True)
        raise
