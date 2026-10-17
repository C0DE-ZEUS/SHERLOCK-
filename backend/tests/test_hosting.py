"""Single-URL hosting: static frontend serving, rate limits, busy handling."""

import threading

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import routes
from app.errors import SherlockError
from app.services import limits
from app.services.limits import RateLimiter
from app.static_site import mount_frontend
from tests import synthetic as s


@pytest.fixture()
def site(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><title>Sherlock</title>")
    (tmp_path / "assets" / "app-123.js").write_text("console.log('hi')")
    (tmp_path.parent / "secret.txt").write_text("outside the static folder")
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)  # as in hosted mode

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    mount_frontend(app, tmp_path)
    return TestClient(app)


def test_serves_index_and_assets(site):
    r = site.get("/")
    assert r.status_code == 200 and "<title>Sherlock</title>" in r.text
    assert r.headers["cache-control"] == "no-cache"
    asset = site.get("/assets/app-123.js")
    assert asset.status_code == 200 and "immutable" in asset.headers["cache-control"]


def test_unknown_paths_fall_back_to_index(site):
    assert "<title>Sherlock</title>" in site.get("/review/anything").text


def test_api_routes_are_not_swallowed(site):
    assert site.get("/api/health").json() == {"status": "ok"}
    r = site.get("/api/does-not-exist")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    # API docs are hidden in hosted mode and must not fall through to the app page.
    for path in ("/docs", "/openapi.json"):
        assert site.get(path).status_code == 404


def test_static_serving_blocks_traversal(site):
    for path in ["/../secret.txt", "/assets/../../secret.txt", "/%2e%2e/secret.txt"]:
        assert "outside the static folder" not in site.get(path).text


def test_rate_limiter_blocks_after_limit():
    limiter = RateLimiter(limit=3, window_seconds=60)
    for _ in range(3):
        limiter.check("1.2.3.4")
    with pytest.raises(SherlockError) as exc:
        limiter.check("1.2.3.4")
    assert exc.value.status_code == 429
    limiter.check("5.6.7.8")  # other clients are unaffected


def test_scan_endpoint_is_rate_limited(client, monkeypatch):
    monkeypatch.setattr(routes, "rate_limiter", RateLimiter(limit=2, window_seconds=600))
    pdf = s.make_pdf([s.EMAIL])
    for _ in range(2):
        assert client.post("/api/scan", files={"file": ("a.pdf", pdf, "application/pdf")}).status_code == 200
    r = client.post("/api/scan", files={"file": ("a.pdf", pdf, "application/pdf")})
    assert r.status_code == 429 and r.json()["error"]["code"] == "rate_limited"


def test_busy_server_fails_politely(monkeypatch):
    monkeypatch.setattr(limits, "_jobs", threading.BoundedSemaphore(1))
    with limits.job_slot():
        with pytest.raises(SherlockError) as exc:
            with limits.job_slot(wait_seconds=0.05):
                pass
    assert exc.value.status_code == 503 and exc.value.code == "server_busy"


def test_health_reports_deployment_and_security_headers(client):
    r = client.get("/api/health")
    assert r.json()["deployment"] in {"local", "hosted"}
    assert r.json()["session_ttl_minutes"] == 30
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert r.headers["x-content-type-options"] == "nosniff"
