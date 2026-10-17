"""HTTP endpoints. Handlers are plain ``def`` so FastAPI runs the CPU-bound
PDF/OCR work in its thread pool instead of blocking the event loop."""

from __future__ import annotations

import time

from fastapi import APIRouter, File, Request, Response, UploadFile
from fastapi.responses import FileResponse

from app.config import settings
from app.schemas.models import (
    AIJobOut,
    AIStatusOut,
    Box,
    FindingOut,
    HealthResponse,
    PageOut,
    RedactRequest,
    RedactResponse,
    ScanResponse,
)
from app.services import redaction
from app.services.ai.jobs import start_ai_job
from app.services.ai.providers import get_provider
from app.services.client_ocr import OCRSubmission, apply_client_ocr, ocr_page_image
from app.services.file_security import ALLOWED_EXTENSIONS
from app.services.limits import job_slot, rate_limiter
from app.services.previews import render_preview
from app.services.scanner import scan_upload
from app.services.sessions import Finding, PageInfo, Session, store
from app.services.text_extraction import ocr_status

router = APIRouter(prefix="/api")

NO_STORE = {"Cache-Control": "no-store"}


def _client_key(request: Request) -> str:
    # Behind a hosting proxy, uvicorn's --proxy-headers sets this to the real client.
    return request.client.host if request.client else "unknown"


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    ok, message = ocr_status()
    ai = get_provider().status()
    return HealthResponse(
        status="ok",
        ai=AIStatusOut(
            enabled=settings.ai_enabled,
            available=ai.available,
            provider=ai.provider,
            model=ai.model,
            endpoint_host=ai.endpoint_host,
            is_local=ai.is_local,
            message=ai.message,
        ),
        deployment=settings.deployment,  # type: ignore[arg-type]
        session_ttl_minutes=settings.session_ttl_seconds // 60,
        ocr_available=ok,
        ocr_message=message,
        max_upload_mb=settings.max_upload_bytes // (1024 * 1024),
        max_pdf_pages=settings.max_pdf_pages,
        accepted_extensions=sorted(ALLOWED_EXTENSIONS),
    )


def _boxes(finding: Finding, page: PageInfo) -> list[Box]:
    return [
        Box(
            x=max(0.0, r[0] / page.width),
            y=max(0.0, r[1] / page.height),
            w=min(1.0, (r[2] - r[0]) / page.width),
            h=min(1.0, (r[3] - r[1]) / page.height),
        )
        for r in finding.rects
    ]


def _scan_response(session: Session) -> ScanResponse:
    job = session.ai_job
    return ScanResponse(
        ai=AIJobOut(
            state=job.state,  # type: ignore[arg-type]
            chunks_total=job.chunks_total,
            chunks_done=job.chunks_done,
            added=job.added,
            confirmed=job.confirmed,
            rejected=job.rejected,
            truncated=job.truncated,
            message=job.message,
            elapsed_seconds=int((job.finished_at or time.time()) - job.started_at),
        ) if job else None,
        session_id=session.id,
        kind=session.kind,  # type: ignore[arg-type]
        file_name=f"{session.upload.display_stem}{session.upload.extension}",
        pages=[
            PageOut(page=p.index + 1, width=p.width, height=p.height, source=p.source)  # type: ignore[arg-type]
            for p in session.pages
        ],
        findings=[
            FindingOut(
                id=f.id,
                category=f.category,
                label=f.label,
                risk=f.risk,  # type: ignore[arg-type]
                detail=f.detail,
                masked=f.masked,
                value=f.value,
                explanation=f.explanation,
                page=f.page_index + 1,
                source=f.source,  # type: ignore[arg-type]
                origin=f.origin,  # type: ignore[arg-type]
                confidence=f.confidence,
                ai_reason=f.ai_reason,
                locatable=f.locatable,
                boxes=_boxes(f, session.pages[f.page_index]),
                # AI-only findings are suggestions: the user opts in to them.
                default_selected=f.locatable and f.risk != "low" and f.origin != "ai",
            )
            for f in list(session.findings.values())
        ],
        warnings=session.warnings,
    )


@router.post("/scan", response_model=ScanResponse)
def scan(request: Request, file: UploadFile = File(...)) -> ScanResponse:
    rate_limiter.check(_client_key(request))
    # Read one byte past the limit so oversized uploads are detected without
    # buffering arbitrarily large bodies.
    data = file.file.read(settings.max_upload_bytes + 1)
    with job_slot():
        session = scan_upload(file.filename, file.content_type, data)
    return _scan_response(session)


@router.get("/session/{session_id}", response_model=ScanResponse)
def get_session(session_id: str) -> ScanResponse:
    return _scan_response(store.get(session_id))


@router.get("/session/{session_id}/ocr-image/{page}")
def ocr_image(session_id: str, page: int) -> Response:
    """Page image for in-browser OCR of pages the server could not read."""
    session = store.get(session_id)
    png = ocr_page_image(session, page)
    return Response(png, media_type="image/png", headers=NO_STORE)


@router.post("/session/{session_id}/ocr", response_model=ScanResponse)
def submit_ocr(request: Request, session_id: str, body: OCRSubmission) -> ScanResponse:
    rate_limiter.check(_client_key(request))
    session = store.get(session_id)
    with job_slot():
        apply_client_ocr(session, body)
    return _scan_response(session)


@router.post("/session/{session_id}/ai", response_model=ScanResponse)
def start_ai(request: Request, session_id: str) -> ScanResponse:
    """Queue contextual AI detection. Returns at once; poll GET for progress."""
    session = store.get(session_id)
    if session.ai_job is None:
        rate_limiter.check(_client_key(request))
    start_ai_job(session)
    return _scan_response(session)


@router.get("/session/{session_id}/ai", response_model=ScanResponse)
def ai_progress(session_id: str) -> ScanResponse:
    return _scan_response(store.get(session_id))


@router.get("/session/{session_id}/preview/{page}")
def preview(session_id: str, page: int) -> Response:
    session = store.get(session_id)
    png = render_preview(session.work_path, session.kind, page - 1, len(session.pages))
    return Response(png, media_type="image/png", headers=NO_STORE)


@router.delete("/session/{session_id}", status_code=204)
def delete_session(session_id: str) -> Response:
    # Idempotent: clearing an already-expired session is not an error.
    store.delete(session_id)
    return Response(status_code=204)


@router.post("/redact", response_model=RedactResponse)
def redact(request: Request, body: RedactRequest) -> RedactResponse:
    rate_limiter.check(_client_key(request))
    session = store.get(body.session_id)
    with job_slot():
        output = redaction.redact(session, body.finding_ids)
    checks = (
        [
            "Selected text removed from the PDF content (not just covered)",
            "Re-opened the output and confirmed the selected text is no longer extractable",
            "Links over redacted areas removed",
            "Document metadata, comments, bookmarks, attachments and scripts removed",
        ]
        if session.kind == "pdf"
        else [
            "Pixels inside each selected area replaced with solid black",
            "Re-opened the output and confirmed every redacted area is fully replaced",
            "Image metadata (EXIF, ICC, text chunks) removed; saved as a new "
            + ("JPEG" if output.media_type == "image/jpeg" else "PNG"),
        ]
    )
    if session.kind == "pdf" and any(
        session.pages[session.findings[fid].page_index].source == "ocr" for fid in body.finding_ids
    ):
        checks.append("Scanned pages with redactions were flattened to a single new image")
    return RedactResponse(
        download_token=output.token,
        file_name=output.filename,
        media_type=output.media_type,
        page_count=output.page_count,
        redacted_count=len(set(body.finding_ids)),
        checks=checks,
    )


@router.get("/download/{token}")
def download(token: str) -> FileResponse:
    _, output = store.get_output(token)
    return FileResponse(
        output.path,
        media_type=output.media_type,
        filename=output.filename,
        headers=NO_STORE,
    )


@router.get("/download/{token}/preview/{page}")
def output_preview(token: str, page: int) -> Response:
    session, output = store.get_output(token)
    png = render_preview(output.path, session.kind, page - 1, output.page_count)
    return Response(png, media_type="image/png", headers=NO_STORE)

