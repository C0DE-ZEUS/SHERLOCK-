"""Pydantic request and response schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Risk = Literal["high", "medium", "low"]


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody


class AIStatusOut(BaseModel):
    enabled: bool
    available: bool
    provider: str
    model: str
    endpoint_host: str
    is_local: bool = Field(description="True when the model runs on the same machine as the backend.")
    message: str


class HealthResponse(BaseModel):
    status: Literal["ok"]
    ai: AIStatusOut
    deployment: Literal["local", "hosted"]
    session_ttl_minutes: int
    ocr_available: bool
    ocr_message: str
    max_upload_mb: int
    max_pdf_pages: int
    accepted_extensions: list[str]


class Box(BaseModel):
    """A highlight box as fractions (0-1) of the page width/height."""

    x: float
    y: float
    w: float
    h: float


class FindingOut(BaseModel):
    id: str
    category: str
    label: str
    risk: Risk
    detail: str
    masked: str
    value: str = Field(description="Full match, shown only when the user chooses to reveal it.")
    explanation: str
    page: int = Field(description="1-based page number (always 1 for images).")
    source: Literal["text", "ocr"]
    origin: Literal["rule", "ai", "rule+ai"]
    confidence: float | None = Field(default=None, description="Model confidence for AI suggestions.")
    ai_reason: str = ""
    locatable: bool
    boxes: list[Box]
    default_selected: bool


class PageOut(BaseModel):
    page: int
    width: float
    height: float
    source: Literal["text", "ocr", "pending", "none"]


class AIJobOut(BaseModel):
    state: Literal["queued", "running", "done", "failed", "unavailable"]
    chunks_total: int
    chunks_done: int
    added: int
    confirmed: int
    rejected: int
    truncated: bool
    message: str
    elapsed_seconds: int


class ScanResponse(BaseModel):
    session_id: str
    kind: Literal["pdf", "image"]
    file_name: str
    pages: list[PageOut]
    findings: list[FindingOut]
    warnings: list[str]
    ai: AIJobOut | None = None


class RedactRequest(BaseModel):
    session_id: str = Field(min_length=10, max_length=100)
    finding_ids: list[str] = Field(max_length=1000)


class RedactResponse(BaseModel):
    download_token: str
    file_name: str
    media_type: str
    page_count: int
    redacted_count: int
    checks: list[str]
