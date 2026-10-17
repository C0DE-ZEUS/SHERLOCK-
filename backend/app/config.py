"""Runtime configuration for the Sherlock backend.

All values have safe defaults so the app runs without any configuration.
Each one can be overridden with an environment variable (see .env.example);
start uvicorn with ``--env-file .env`` to load them from a file.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

AI_PROVIDERS = ("ollama", "openai_compatible", "none")


@dataclass(frozen=True)
class Settings:
    # Upload limits
    max_upload_bytes: int
    max_pdf_pages: int
    max_image_pixels: int

    # Temporary storage. Only Sherlock's own session folders under this
    # directory are ever deleted (on startup, reset, and expiry).
    temp_dir: Path
    session_ttl_seconds: int
    max_sessions: int

    # Server-side OCR (optional; the browser can OCR instead)
    tesseract_cmd: str | None
    ocr_lang: str
    ocr_dpi: int
    raster_output_dpi: int
    preview_dpi: int
    client_ocr_dpi: int

    # "local" (runs on the user's own machine) or "hosted" (deployed for
    # others). Changes privacy wording and hides the interactive API docs.
    deployment: str
    # Built frontend to serve from the backend for single-URL deployments.
    static_dir: Path | None

    # Abuse protection
    rate_limit_requests: int
    rate_limit_window_seconds: int
    max_concurrent_jobs: int

    # CORS allow-list
    allowed_origins: list[str]

    # Contextual AI detection
    ai_provider: str  # "ollama" | "openai_compatible" | "none"
    ai_base_url: str
    ai_model: str
    ai_api_key: str | None
    ai_timeout_seconds: int
    ai_max_chars: int  # total document text sent to the model per scan
    ai_chunk_chars: int  # text per model call

    @property
    def ai_enabled(self) -> bool:
        return self.ai_provider != "none"


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Build settings from environment variables (``os.environ`` by default)."""
    env = os.environ if env is None else env

    def get_int(name: str, default: int, minimum: int = 1) -> int:
        raw = (env.get(name) or "").strip()
        try:
            value = int(raw) if raw else default
        except ValueError:
            value = default
        return max(minimum, value)

    def get_list(name: str, default: list[str]) -> list[str]:
        raw = env.get(name)
        if not raw:
            return default
        return [item.strip().rstrip("/") for item in raw.split(",") if item.strip()]

    provider = (env.get("SHERLOCK_AI_PROVIDER") or "ollama").strip().lower()
    if provider not in AI_PROVIDERS:
        provider = "none"
    default_base = "http://localhost:11434" if provider == "ollama" else ""

    return Settings(
        max_upload_bytes=get_int("SHERLOCK_MAX_UPLOAD_MB", 10) * 1024 * 1024,
        max_pdf_pages=get_int("SHERLOCK_MAX_PDF_PAGES", 30),
        max_image_pixels=40_000_000,
        temp_dir=Path(env.get("SHERLOCK_TEMP_DIR") or Path(tempfile.gettempdir()) / "sherlock-work"),
        session_ttl_seconds=get_int("SHERLOCK_SESSION_TTL_MINUTES", 30) * 60,
        max_sessions=get_int("SHERLOCK_MAX_SESSIONS", 20),
        tesseract_cmd=env.get("SHERLOCK_TESSERACT_CMD") or None,
        ocr_lang=env.get("SHERLOCK_OCR_LANG") or "eng",
        ocr_dpi=300,
        raster_output_dpi=200,
        preview_dpi=110,
        client_ocr_dpi=200,
        deployment="hosted" if env.get("SHERLOCK_DEPLOYMENT") == "hosted" else "local",
        static_dir=Path(env["SHERLOCK_STATIC_DIR"]) if env.get("SHERLOCK_STATIC_DIR") else None,
        rate_limit_requests=get_int("SHERLOCK_RATE_LIMIT", 30, minimum=0),
        rate_limit_window_seconds=600,
        max_concurrent_jobs=get_int("SHERLOCK_MAX_CONCURRENT_JOBS", 2),
        allowed_origins=get_list(
            "SHERLOCK_ALLOWED_ORIGINS", ["http://localhost:5173", "http://127.0.0.1:5173"]
        ),
        ai_provider=provider,
        ai_base_url=(env.get("SHERLOCK_AI_BASE_URL") or default_base).strip().rstrip("/"),
        ai_model=(env.get("SHERLOCK_AI_MODEL") or "qwen3:4b").strip(),
        ai_api_key=env.get("SHERLOCK_AI_API_KEY") or None,
        ai_timeout_seconds=get_int("SHERLOCK_AI_TIMEOUT_SECONDS", 180),
        ai_max_chars=get_int("SHERLOCK_AI_MAX_CHARS", 6000, minimum=200),
        ai_chunk_chars=get_int("SHERLOCK_AI_CHUNK_CHARS", 2000, minimum=200),
    )


settings = load_settings()
