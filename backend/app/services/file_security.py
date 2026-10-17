"""Upload validation and safe file handling.

Uploaded bytes are treated as untrusted. A file is accepted only when its
extension, declared MIME type, and actual file signature all agree. The
uploaded filename is never used as a filesystem path; it is only reduced to a
safe display stem for the download name.
"""

from __future__ import annotations

import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path, PurePath

from app.config import settings
from app.errors import SherlockError

ALLOWED_EXTENSIONS = {".pdf": "pdf", ".png": "png", ".jpg": "jpeg", ".jpeg": "jpeg"}

ALLOWED_MIME = {
    "pdf": {"application/pdf", "application/x-pdf"},
    "png": {"image/png"},
    "jpeg": {"image/jpeg", "image/jpg", "image/pjpeg"},
}
# Some browsers and tools send a generic type; the signature check still applies.
GENERIC_MIME = {"", "application/octet-stream", "binary/octet-stream"}


@dataclass(frozen=True)
class ValidatedUpload:
    format: str  # "pdf" | "png" | "jpeg"
    extension: str  # normalised, e.g. ".pdf"
    display_stem: str  # safe for use in a download filename

    @property
    def is_pdf(self) -> bool:
        return self.format == "pdf"


def _signature_format(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    # The PDF spec tolerates a small amount of junk before the header.
    if b"%PDF-" in data[:1024]:
        return "pdf"
    return None


def safe_display_stem(filename: str | None) -> str:
    """Reduce an untrusted filename to a short, harmless stem."""
    name = PurePath((filename or "").replace("\\", "/")).name
    stem = name.rsplit(".", 1)[0] if "." in name else name
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("-._")
    return (stem or "document")[:60]


def validate_upload(filename: str | None, content_type: str | None, data: bytes) -> ValidatedUpload:
    if not data:
        raise SherlockError("empty_file", "The uploaded file is empty.")
    if len(data) > settings.max_upload_bytes:
        limit_mb = settings.max_upload_bytes // (1024 * 1024)
        raise SherlockError(
            "file_too_large",
            f"This file is larger than the {limit_mb} MB limit.",
            status_code=413,
        )

    name = PurePath((filename or "").replace("\\", "/")).name
    extension = ("." + name.rsplit(".", 1)[1].lower()) if "." in name else ""
    expected = ALLOWED_EXTENSIONS.get(extension)
    if expected is None:
        raise SherlockError(
            "unsupported_file_type",
            "Unsupported file type. Upload a PDF, PNG, JPG, or JPEG file.",
            status_code=415,
        )

    mime = (content_type or "").split(";")[0].strip().lower()
    if mime not in GENERIC_MIME and mime not in ALLOWED_MIME[expected]:
        raise SherlockError(
            "unsupported_file_type",
            "The file type reported by your browser does not match the file extension.",
            status_code=415,
        )

    actual = _signature_format(data)
    if actual != expected:
        raise SherlockError(
            "signature_mismatch",
            "The file contents do not match its extension. The file may be corrupt or mislabelled.",
            status_code=415,
        )

    return ValidatedUpload(
        format=expected,
        extension=".jpg" if expected == "jpeg" else extension,
        display_stem=safe_display_stem(filename),
    )


def ensure_inside(base: Path, candidate: Path) -> Path:
    """Resolve ``candidate`` and guarantee it stays inside ``base``."""
    base_resolved = base.resolve()
    resolved = candidate.resolve()
    if base_resolved != resolved and base_resolved not in resolved.parents:
        raise SherlockError("invalid_path", "Invalid file reference.", status_code=400)
    return resolved


_SESSION_DIR = re.compile(r"[0-9a-f]{32}")


def clean_temp_root(max_age_seconds: float | None = None) -> int:
    """Delete session folders in the temp root. Returns the number removed.

    With ``max_age_seconds=None`` every session folder is removed (used at
    startup, because sessions are held in memory and do not survive a restart).
    Only folders named like Sherlock's own (32 hex characters) are touched, so
    a misconfigured SHERLOCK_TEMP_DIR can never wipe unrelated files.
    """
    root = settings.temp_dir
    if not root.exists():
        return 0
    removed = 0
    now = time.time()
    for child in root.iterdir():
        if not (child.is_dir() and _SESSION_DIR.fullmatch(child.name)):
            continue
        try:
            if max_age_seconds is not None and now - child.stat().st_mtime < max_age_seconds:
                continue
            shutil.rmtree(child, ignore_errors=True)
            removed += 1
        except OSError:
            continue
    return removed
