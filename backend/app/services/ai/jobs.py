"""Background AI scans.

A local 4B model on a laptop CPU can take a minute or more per chunk, so AI
detection never blocks the upload request. ``start_ai_job`` queues one job
per session on a single worker thread (one model call at a time keeps memory
use predictable); the browser polls ``AIJob`` for progress. Results are
merged into the session's findings, deduplicated against rule findings.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor

from app.config import settings
from app.errors import SherlockError
from app.services.ai.detector import AI_TYPES, AIMatch, run_ai_detection
from app.services.ai.providers import get_provider
from app.services.detection import mask_value
from app.services.sessions import AIJob, Finding, Session, store
from app.services.text_extraction import PageText

log = logging.getLogger("sherlock.ai")

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sherlock-ai")

ACTIVE_STATES = {"queued", "running"}


def start_ai_job(session: Session) -> AIJob:
    with session.lock:
        job = session.ai_job
        # Re-use a running or finished job: identical content is never re-sent.
        if job is not None and job.state in ACTIVE_STATES | {"done"}:
            return job
        if any(p.source == "pending" for p in session.pages):
            raise SherlockError(
                "ocr_pending", "Finish reading the document with OCR before running AI detection.", 409
            )

        status = get_provider().status()
        if not status.available:
            session.ai_job = AIJob(state="unavailable", message=status.message, finished_at=time.time())
            return session.ai_job

        session.ai_job = AIJob(state="queued", message="Waiting for the AI model.")
        _executor.submit(_run, session.id)
        return session.ai_job


def mask_known(session: Session) -> list[PageText]:
    """Copies of the page texts with rule findings blanked out ('#', same length).

    The model then spends its (slow, on a laptop) output only on things the
    rules missed, and values the rules already caught - emails, card numbers,
    keys - are never sent to the model at all. Offsets are unchanged, so model
    evidence still maps back to the original text.
    """
    masked: list[PageText] = []
    for page in session.page_texts:
        chars = list(page.text)
        for f in session.findings.values():
            if f.page_index == page.index and f.origin != "ai":
                for i in range(f.span[0], min(f.span[1], len(chars))):
                    if not chars[i].isspace():
                        chars[i] = "#"
        masked.append(PageText(page.index, page.width, page.height, page.source, text="".join(chars)))
    return masked


def _run(session_id: str) -> None:
    session = store.peek(session_id)
    if session is None:
        return
    job = session.ai_job
    assert job is not None
    job.state = "running"
    job.message = "Analysing text with the AI model."
    started = time.monotonic()

    def progress(done: int, total: int) -> None:
        job.chunks_done, job.chunks_total = done, total

    try:
        result = run_ai_detection(
            get_provider(),
            mask_known(session),
            settings.ai_max_chars,
            settings.ai_chunk_chars,
            on_progress=progress,
            should_stop=lambda: store.peek(session_id) is None,
        )
    except Exception:  # never let a worker crash silently
        log.exception("AI job crashed")
        job.state, job.message, job.finished_at = "failed", "AI detection failed unexpectedly.", time.time()
        return

    if store.peek(session_id) is None:  # session was cleared meanwhile
        return

    job.chunks_total = result.chunks_total
    job.chunks_done = result.chunks_done
    job.truncated = result.truncated
    job.rejected = result.rejected
    with session.lock:
        added, confirmed = merge_ai_matches(session, result.matches)
    job.added, job.confirmed = added, confirmed
    job.finished_at = time.time()

    if result.error and not result.matches:
        job.state, job.message = "failed", result.error
    else:
        job.state = "done"
        parts = [f"{added} new suggestion(s)" if added else "No additional sensitive information found"]
        if confirmed:
            parts.append(f"{confirmed} rule finding(s) confirmed")
        if result.chunks_failed:
            parts.append(f"{result.chunks_failed} part(s) could not be analysed")
        if result.truncated:
            parts.append("only the first part of the document was analysed")
        job.message = "; ".join(parts) + "."
    log.info(
        "AI job %s: chunks=%d failed=%d added=%d confirmed=%d rejected=%d seconds=%.1f",
        job.state, result.chunks_total, result.chunks_failed, added, confirmed,
        result.rejected, time.monotonic() - started,
    )


def merge_ai_matches(session: Session, matches: list[AIMatch]) -> tuple[int, int]:
    """Add AI matches as findings, deduplicating against existing ones.

    A match overlapping an existing finding on the same page does not create
    a new finding; the existing one is marked as also flagged by AI.
    Returns (new findings, confirmed existing findings).
    """
    added = confirmed = 0
    for m in sorted(matches, key=lambda m: (m.page_index, m.start, -(m.end - m.start))):
        overlapping = [
            f for f in session.findings.values()
            if f.page_index == m.page_index and f.span[0] < m.end and m.start < f.span[1]
        ]
        if overlapping:
            for f in overlapping:
                if f.origin == "rule":
                    f.origin = "rule+ai"
                    f.ai_reason = m.reason
                    confirmed += 1
            continue

        page = session.page_texts[m.page_index]
        value = page.text[m.start : m.end]  # original text, never the masked copy
        if "#" * 3 in value:
            continue
        label, explanation = AI_TYPES[m.type]
        finding_id = session.next_id("a")
        session.findings[finding_id] = Finding(
            id=finding_id,
            category=f"ai_{m.type}",
            label=label,
            risk=m.risk,
            value=value,
            masked=mask_value("ai", value),
            explanation=explanation,
            detail="AI suggestion",
            page_index=m.page_index,
            rects=page.locate(m.start, m.end),
            source=page.source,
            span=(m.start, m.end),
            origin="ai",
            confidence=round(m.confidence, 2),
            ai_reason=m.reason,
        )
        added += 1
    return added, confirmed
