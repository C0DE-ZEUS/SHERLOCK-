"""Browser OCR submissions, real Tesseract OCR, configuration, deployment files."""

import io
from pathlib import Path

import pymupdf
import pytest
from PIL import Image, ImageDraw, ImageFont

from app.config import load_settings
from app.services import text_extraction
from tests import synthetic as s

ROOT = Path(__file__).resolve().parents[2]


def scan(client, name, data, mime):
    r = client.post("/api/scan", files={"file": (name, data, mime)})
    assert r.status_code == 200, r.text
    return r.json()


def ocr_image_size(client, sid, page=1):
    r = client.get(f"/api/session/{sid}/ocr-image/{page}")
    assert r.status_code == 200 and r.content[1:4] == b"PNG"
    return Image.open(io.BytesIO(r.content)).size


def word(text, x0, y0, x1, y1, line=0):
    return {"text": text, "x0": x0, "y0": y0, "x1": x1, "y1": y1, "line": line}


# --------------------------------------------------------------------------
# Browser OCR (Tesseract.js) submissions
# --------------------------------------------------------------------------

def test_browser_ocr_on_image_then_redact(client, no_ocr):
    body = scan(client, "shot.png", s.make_image(), "image/png")
    sid = body["session_id"]
    w, h = ocr_image_size(client, sid)
    assert (w, h) == (400, 200)

    res = client.post(f"/api/session/{sid}/ocr", json={"pages": [{
        "page": 1, "width": w, "height": h,
        "words": [word("Email:", 20, 40, 80, 60), word(s.EMAIL, 90, 40, 300, 60)],
    }]})
    assert res.status_code == 200, res.text
    after = res.json()
    assert after["pages"][0]["source"] == "ocr"
    email = next(f for f in after["findings"] if f["category"] == "email")
    assert email["source"] == "ocr" and email["origin"] == "rule"

    red = client.post("/api/redact", json={"session_id": sid, "finding_ids": [email["id"]]})
    assert red.status_code == 200, red.text
    out = Image.open(io.BytesIO(client.get(f"/api/download/{red.json()['download_token']}").content))
    assert out.convert("RGB").crop((90, 40, 301, 61)).getextrema() == ((0, 0), (0, 0), (0, 0))


def test_browser_ocr_on_scanned_pdf_page_rasterises(client, no_ocr):
    img = Image.new("RGB", (850, 1100), "white")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_image(page.rect, stream=buf.getvalue())
    body = scan(client, "scan.pdf", doc.tobytes(), "application/pdf")
    sid = body["session_id"]
    w, h = ocr_image_size(client, sid)
    k = w / 595  # pixels per PDF point in the served image
    res = client.post(f"/api/session/{sid}/ocr", json={"pages": [{
        "page": 1, "width": w, "height": h,
        "words": [word("Phone", 100 * k, 100 * k, 140 * k, 112 * k), word(s.PHONE, 150 * k, 100 * k, 260 * k, 112 * k)],
    }]})
    phone = next(f for f in res.json()["findings"] if f["category"] == "phone")
    red = client.post("/api/redact", json={"session_id": sid, "finding_ids": [phone["id"]]})
    assert red.status_code == 200, red.text
    out = pymupdf.open(stream=client.get(f"/api/download/{red.json()['download_token']}").content, filetype="pdf")
    assert out[0].get_text().strip() == "" and len(out[0].get_images()) == 1
    assert max(out[0].get_pixmap(dpi=72, clip=pymupdf.Rect(152, 102, 258, 110)).samples) < 40


def test_browser_ocr_submissions_are_validated(client, no_ocr):
    sid = scan(client, "shot.png", s.make_image(), "image/png")["session_id"]
    page = {"page": 1, "width": 400, "height": 200, "words": [word("hello", 1, 1, 50, 20)]}

    # Must fetch the page image first (its size is recorded server-side).
    r = client.post(f"/api/session/{sid}/ocr", json={"pages": [page]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "invalid_ocr"

    ocr_image_size(client, sid)
    wrong_size = dict(page, width=999)
    assert client.post(f"/api/session/{sid}/ocr", json={"pages": [wrong_size]}).status_code == 409
    assert client.post(f"/api/session/{sid}/ocr", json={"pages": [dict(page, page=2)]}).status_code == 409
    too_long = dict(page, words=[word("x" * 500, 1, 1, 5, 5)])
    assert client.post(f"/api/session/{sid}/ocr", json={"pages": [too_long]}).status_code == 422

    # Out-of-bounds boxes are clamped to the image, never trusted blindly.
    wild = dict(page, words=[word(s.EMAIL, -50, -50, 9999, 9999)])
    ok = client.post(f"/api/session/{sid}/ocr", json={"pages": [wild]})
    assert ok.status_code == 200
    box = ok.json()["findings"][0]["boxes"][0]
    assert 0 <= box["x"] and 0 <= box["y"] and box["x"] + box["w"] <= 1.0001 and box["y"] + box["h"] <= 1.0001

    # A page cannot be OCR'd twice.
    assert client.post(f"/api/session/{sid}/ocr", json={"pages": [page]}).status_code == 409
    assert client.get(f"/api/session/{sid}/ocr-image/1").status_code == 409


# --------------------------------------------------------------------------
# Real server-side OCR (runs only where Tesseract is installed)
# --------------------------------------------------------------------------

def _tesseract_ready() -> bool:
    text_extraction.ocr_status.cache_clear()
    return text_extraction.ocr_status()[0]


@pytest.mark.skipif(not _tesseract_ready(), reason="Tesseract is not installed on this machine")
def test_real_tesseract_reads_and_redacts_an_image(client):
    image = Image.new("RGB", (1200, 260), "white")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("arial.ttf", 40)
    except OSError:
        font = ImageFont.load_default(size=40)
    draw.text((30, 40), "Contact: ravi.sample@example.com", fill="black", font=font)
    draw.text((30, 150), "PAN: ABCPE1234F", fill="black", font=font)
    buf = io.BytesIO()
    image.save(buf, "PNG")

    body = scan(client, "real.png", buf.getvalue(), "image/png")
    values = {f["category"]: f for f in body["findings"]}
    assert values["email"]["value"] == "ravi.sample@example.com"
    assert values["pan"]["value"] == "ABCPE1234F"

    ids = [values["email"]["id"], values["pan"]["id"]]
    red = client.post("/api/redact", json={"session_id": body["session_id"], "finding_ids": ids})
    assert red.status_code == 200, red.text
    out = Image.open(io.BytesIO(client.get(f"/api/download/{red.json()['download_token']}").content))
    # Re-OCR the output: the redacted values must be unreadable now.
    text = " ".join(w.text for w in text_extraction.ocr_words(out.convert("RGB")))
    assert "ravi.sample" not in text and "ABCPE1234F" not in text
    assert "Contact" in text  # unredacted words remain readable


# --------------------------------------------------------------------------
# Configuration from environment variables
# --------------------------------------------------------------------------

def test_settings_defaults():
    cfg = load_settings({})
    assert cfg.max_upload_bytes == 10 * 1024 * 1024
    assert cfg.ai_provider == "ollama" and cfg.ai_model == "qwen3:4b"
    assert cfg.ai_base_url == "http://localhost:11434"
    assert cfg.deployment == "local" and cfg.static_dir is None
    assert cfg.allowed_origins == ["http://localhost:5173", "http://127.0.0.1:5173"]


def test_settings_from_environment():
    cfg = load_settings({
        "SHERLOCK_MAX_UPLOAD_MB": "5",
        "SHERLOCK_AI_PROVIDER": "openai_compatible",
        "SHERLOCK_AI_BASE_URL": "https://ai.example.com/v1/",
        "SHERLOCK_AI_MODEL": "small-model",
        "SHERLOCK_AI_MAX_CHARS": "3000",
        "SHERLOCK_ALLOWED_ORIGINS": "https://sherlock.example.com/, https://www.example.com",
        "SHERLOCK_DEPLOYMENT": "hosted",
        "SHERLOCK_STATIC_DIR": "/app/static",
    })
    assert cfg.max_upload_bytes == 5 * 1024 * 1024
    assert cfg.ai_provider == "openai_compatible" and cfg.ai_base_url == "https://ai.example.com/v1"
    assert cfg.ai_model == "small-model" and cfg.ai_max_chars == 3000
    assert cfg.allowed_origins == ["https://sherlock.example.com", "https://www.example.com"]
    assert cfg.deployment == "hosted" and cfg.static_dir == Path("/app/static")


def test_settings_reject_bad_values():
    cfg = load_settings({
        "SHERLOCK_MAX_UPLOAD_MB": "lots", "SHERLOCK_AI_PROVIDER": "gpt-please",
        "SHERLOCK_AI_TIMEOUT_SECONDS": "-5", "SHERLOCK_DEPLOYMENT": "weird",
    })
    assert cfg.max_upload_bytes == 10 * 1024 * 1024
    assert cfg.ai_provider == "none"  # unknown providers are never guessed
    assert cfg.ai_timeout_seconds >= 1 and cfg.deployment == "local"


# --------------------------------------------------------------------------
# Deployment configuration files
# --------------------------------------------------------------------------

def test_deployment_files_are_safe_defaults():
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert "SHERLOCK_DEPLOYMENT=hosted" in dockerfile
    assert "SHERLOCK_AI_PROVIDER=none" in dockerfile  # a public server never reaches a laptop model
    assert "USER sherlock" in dockerfile and "/api/health" in dockerfile
    assert "--no-access-log" in dockerfile  # URLs carry session tokens
    render = (ROOT / "render.yaml").read_text()
    assert "healthCheckPath: /api/health" in render
    for example in (ROOT / "backend" / ".env.example", ROOT / "frontend" / ".env.example"):
        text = example.read_text()
        assert "sk-" not in text and "ghp_" not in text and "AKIA" not in text
    ignored = (ROOT / ".gitignore").read_text()
    assert ".env" in ignored and "node_modules/" in ignored and ".venv/" in ignored
