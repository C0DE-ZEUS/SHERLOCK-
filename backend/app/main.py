"""Sherlock backend entry point.

Run with:  uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import router
from app.config import settings
from app.errors import SherlockError
from app.services.file_security import clean_temp_root
from app.services.sessions import store
from app.services.text_extraction import ocr_status
from app.static_site import mount_frontend

# Logs carry event names and counts only - never document text or detected values.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("sherlock")
# httpx logs every model request URL at INFO; keep it quiet.
logging.getLogger("httpx").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.temp_dir.mkdir(parents=True, exist_ok=True)
    removed = clean_temp_root()  # sessions are in memory, so leftovers are stale
    if removed:
        log.info("removed %d stale temporary item(s)", removed)
    ok, message = ocr_status()
    log.info("OCR %s: %s", "available" if ok else "unavailable", message)
    yield
    store.clear()


_hosted = settings.deployment == "hosted"
app = FastAPI(
    title="Sherlock",
    description="Find the hidden. Protect the personal.",
    version="1.0.0",
    lifespan=lifespan,
    # Interactive API docs are a development aid; hide them on public deployments.
    docs_url=None if _hosted else "/docs",
    redoc_url=None,
    openapi_url=None if _hosted else "/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
    expose_headers=["Content-Disposition"],
)


# The app loads nothing from third parties. Inline styles are needed for the
# percentage-positioned highlight boxes; 'wasm-unsafe-eval' and worker-src let
# the self-hosted Tesseract.js engine run in a web worker. /docs (local mode
# only) loads Swagger UI from a CDN, so it is exempt.
CSP = (
    "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self'; "
    "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self' data:; "
    "font-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; "
    "frame-ancestors 'none'"
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-Frame-Options", "DENY")
    if request.url.path != "/docs":
        response.headers.setdefault("Content-Security-Policy", CSP)
    return response


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


@app.exception_handler(SherlockError)
async def sherlock_error_handler(_: Request, exc: SherlockError) -> JSONResponse:
    return _error(exc.status_code, exc.code, exc.message)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    return _error(422, "invalid_request", "The request was missing a file or had invalid fields.")


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = "not_found" if exc.status_code == 404 else "http_error"
    message = "Not found." if exc.status_code == 404 else str(exc.detail)
    return _error(exc.status_code, code, message)


@app.exception_handler(Exception)
async def unexpected_error_handler(_: Request, exc: Exception) -> JSONResponse:
    log.error("unexpected error: %s", type(exc).__name__)
    return _error(500, "internal_error", "Something went wrong while processing the file.")


app.include_router(router)

# Single-URL deployments: serve the built frontend. Must come after the router.
if settings.static_dir is not None:
    mount_frontend(app, settings.static_dir)
