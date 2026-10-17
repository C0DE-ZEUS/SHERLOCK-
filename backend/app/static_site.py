"""Serve the built React app from the backend (single-URL deployments)."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse

from app.errors import SherlockError
from app.services.file_security import ensure_inside


def mount_frontend(app: FastAPI, static_dir: Path) -> None:
    """Serve files from ``static_dir`` and fall back to index.html.

    Must be called after the API router is included, so /api routes win.
    """
    root = static_dir.resolve()
    index = root / "index.html"

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        if path == "api" or path.startswith("api/") or path in {"docs", "redoc", "openapi.json"}:
            return JSONResponse(
                status_code=404, content={"error": {"code": "not_found", "message": "Not found."}}
            )
        if path:
            try:
                candidate = ensure_inside(root, root / path)
            except SherlockError:
                return FileResponse(index)
            if candidate.is_file():
                # Hashed build assets never change; the HTML shell always revalidates.
                cache = "public, max-age=31536000, immutable" if path.startswith("assets/") else "no-cache"
                return FileResponse(candidate, headers={"Cache-Control": cache})
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
