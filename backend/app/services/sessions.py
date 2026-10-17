"""In-memory scan sessions backed by an isolated temp folder per session.

There is no database. A session holds the server-side truth about a scan
(findings, their exact coordinates, the stored upload) so the client only ever
sends finding IDs back. Tokens are random and unguessable; no filesystem path
is ever returned to the client.
"""

from __future__ import annotations

import secrets
import shutil
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from app.config import settings
from app.errors import SherlockError
from app.services.file_security import ValidatedUpload
from app.services.text_extraction import PageText, Rect


@dataclass
class Finding:
    id: str
    category: str
    label: str
    risk: str
    value: str
    masked: str
    explanation: str
    detail: str
    page_index: int  # 0-based; images use 0
    rects: list[Rect]  # page units: PDF points, or image pixels
    source: str  # "text" | "ocr"
    span: tuple[int, int] = (0, 0)  # character offsets in the page text
    origin: str = "rule"  # "rule" | "ai" | "rule+ai"
    confidence: float | None = None  # AI findings only
    ai_reason: str = ""  # the model's short explanation, if it flagged this

    @property
    def locatable(self) -> bool:
        return bool(self.rects)


@dataclass
class PageInfo:
    index: int
    width: float
    height: float
    source: str  # "text" | "ocr" | "pending" (awaiting browser OCR) | "none"


@dataclass
class AIJob:
    state: str  # "queued" | "running" | "done" | "failed" | "unavailable"
    chunks_total: int = 0
    chunks_done: int = 0
    added: int = 0  # new AI-only findings
    confirmed: int = 0  # rule findings the model also flagged
    rejected: int = 0  # suggestions dropped by validation
    truncated: bool = False
    message: str = ""
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None


@dataclass
class Output:
    token: str
    path: Path
    filename: str
    media_type: str
    page_count: int


@dataclass
class Session:
    id: str
    upload: ValidatedUpload
    workdir: Path
    # Working copy: a flattened PDF or an orientation-corrected PNG. The
    # user's original bytes are never written to disk or modified.
    work_path: Path
    pages: list[PageInfo] = field(default_factory=list)
    findings: dict[str, Finding] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_access: float = field(default_factory=time.time)
    output: Output | None = None
    # Extracted text with word boxes, kept for AI detection and browser OCR.
    page_texts: list[PageText] = field(default_factory=list)
    ai_job: AIJob | None = None
    # Pixel size of each page image served for browser OCR, by page index.
    ocr_images: dict[int, tuple[int, int]] = field(default_factory=dict)
    lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    def next_id(self, prefix: str) -> str:
        n = sum(1 for fid in self.findings if fid.startswith(prefix)) + 1
        while f"{prefix}{n}" in self.findings:
            n += 1
        return f"{prefix}{n}"

    @property
    def kind(self) -> str:
        return "pdf" if self.upload.is_pdf else "image"


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._outputs: dict[str, str] = {}  # download token -> session id
        self._lock = threading.RLock()

    # -- lifecycle -------------------------------------------------------
    def create_workdir(self) -> tuple[str, Path]:
        session_id = secrets.token_urlsafe(24)
        workdir = settings.temp_dir / secrets.token_hex(16)
        workdir.mkdir(parents=True, exist_ok=False)
        return session_id, workdir

    def add(self, session: Session) -> None:
        with self._lock:
            self.expire()
            while len(self._sessions) >= settings.max_sessions:
                oldest = min(self._sessions.values(), key=lambda s: s.last_access)
                self._remove(oldest.id)
            self._sessions[session.id] = session

    def get(self, session_id: str) -> Session:
        with self._lock:
            self.expire()
            session = self._sessions.get(session_id)
            if session is None:
                raise SherlockError(
                    "session_not_found",
                    "This scan has expired or was cleared. Upload the file again.",
                    404,
                )
            session.last_access = time.time()
            return session

    def set_output(self, session: Session, output: Output) -> None:
        with self._lock:
            if session.output is not None:
                self._outputs.pop(session.output.token, None)
                session.output.path.unlink(missing_ok=True)
            session.output = output
            self._outputs[output.token] = session.id

    def get_output(self, token: str) -> tuple[Session, Output]:
        with self._lock:
            self.expire()
            session_id = self._outputs.get(token)
            session = self._sessions.get(session_id) if session_id else None
            if session is None or session.output is None or session.output.token != token:
                raise SherlockError(
                    "download_not_found", "This download has expired or was cleared.", 404
                )
            session.last_access = time.time()
            return session, session.output

    def peek(self, session_id: str) -> Session | None:
        """Look up a session without refreshing its expiry (background jobs)."""
        with self._lock:
            return self._sessions.get(session_id)

    def delete(self, session_id: str) -> bool:
        with self._lock:
            return self._remove(session_id)

    def expire(self) -> None:
        cutoff = time.time() - settings.session_ttl_seconds
        with self._lock:
            for sid in [s.id for s in self._sessions.values() if s.last_access < cutoff]:
                self._remove(sid)

    def clear(self) -> None:
        with self._lock:
            for sid in list(self._sessions):
                self._remove(sid)

    def __len__(self) -> int:
        return len(self._sessions)

    # -- internals -------------------------------------------------------
    def _remove(self, session_id: str) -> bool:
        session = self._sessions.pop(session_id, None)
        if session is None:
            return False
        if session.output is not None:
            self._outputs.pop(session.output.token, None)
        shutil.rmtree(session.workdir, ignore_errors=True)
        return True


store = SessionStore()
