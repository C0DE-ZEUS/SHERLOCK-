import io

import pymupdf
import pytest
from PIL import Image

from app.config import settings
from app.services.sessions import store
from app.services.text_extraction import Word
from tests import synthetic as s

LINES = [
    f"Contact: {s.EMAIL}",
    f"Phone: {s.PHONE}",
    f"PAN: {s.PAN}",
    f"Account No: {s.ACCOUNT} IFSC {s.IFSC}",
    f"Deploy token {s.GITHUB_TOKEN}",
    "This line is ordinary text and should stay.",
]


def scan(client, name, data, mime):
    r = client.post("/api/scan", files={"file": (name, data, mime)})
    assert r.status_code == 200, r.text
    return r.json()


def by_category(body):
    return {f["category"]: f for f in body["findings"]}


def redact(client, body, ids):
    return client.post("/api/redact", json={"session_id": body["session_id"], "finding_ids": ids})


def download(client, token):
    r = client.get(f"/api/download/{token}")
    assert r.status_code == 200
    return r


# --------------------------------------------------------------------------
# API basics
# --------------------------------------------------------------------------

def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["max_upload_mb"] == 10
    assert set(body["accepted_extensions"]) == {".pdf", ".png", ".jpg", ".jpeg"}


def test_scan_text_pdf(client):
    body = scan(client, "statement.pdf", s.make_pdf(LINES), "application/pdf")
    found = by_category(body)
    assert {"email", "phone", "pan", "bank_account", "ifsc", "secret"} <= set(found)
    assert body["kind"] == "pdf" and body["pages"][0]["source"] == "text"
    email = found["email"]
    assert email["masked"] == "ja***@example.com" and email["page"] == 1
    assert email["locatable"] and email["default_selected"]
    box = email["boxes"][0]
    assert 0 < box["x"] < 1 and 0 < box["y"] < 1 and 0 < box["w"] < 1 and 0 < box["h"] < 1


def test_preview_renders_png(client):
    body = scan(client, "statement.pdf", s.make_pdf(LINES), "application/pdf")
    r = client.get(f"/api/session/{body['session_id']}/preview/1")
    assert r.status_code == 200 and r.content.startswith(b"\x89PNG")
    assert client.get(f"/api/session/{body['session_id']}/preview/2").status_code == 404


def test_redact_rejects_bad_selections(client):
    body = scan(client, "statement.pdf", s.make_pdf(LINES), "application/pdf")
    assert redact(client, body, []).json()["error"]["code"] == "nothing_selected"
    assert redact(client, body, ["f999"]).json()["error"]["code"] == "invalid_selection"
    r = client.post("/api/redact", json={"session_id": "not-a-real-session-id", "finding_ids": ["f1"]})
    assert r.status_code == 404


# --------------------------------------------------------------------------
# PDF redaction is real
# --------------------------------------------------------------------------

def test_pdf_selected_text_removed_unselected_kept(client):
    pdf = s.make_pdf(LINES, metadata={"author": "Synthetic Author", "title": "Synthetic Title"})
    body = scan(client, "statement.pdf", pdf, "application/pdf")
    found = by_category(body)
    selected = [found[c]["id"] for c in ("email", "pan", "bank_account", "secret")]
    r = redact(client, body, selected)
    assert r.status_code == 200, r.text
    assert r.json()["redacted_count"] == 4

    out = pymupdf.open(stream=download(client, r.json()["download_token"]).content, filetype="pdf")
    text = out[0].get_text()
    flat = text.replace(" ", "").replace("\n", "")
    for removed in (s.EMAIL, s.PAN, s.ACCOUNT, s.GITHUB_TOKEN):
        assert removed not in text and removed.replace(" ", "") not in flat
    # Unselected findings and ordinary text are untouched.
    assert s.PHONE in text
    assert s.IFSC in text
    assert "This line is ordinary text and should stay." in text
    # Searching the page (what copy/paste and Ctrl+F use) finds nothing.
    assert out[0].search_for(s.EMAIL) == []
    # Metadata stripped.
    assert out.metadata["author"] == "" and out.metadata["title"] == ""
    assert b"Synthetic Author" not in download(client, r.json()["download_token"]).content


def test_original_working_copy_not_modified(client):
    body = scan(client, "statement.pdf", s.make_pdf(LINES), "application/pdf")
    session = store.get(body["session_id"])
    before = session.work_path.read_bytes()
    redact(client, body, [by_category(body)["email"]["id"]])
    assert session.work_path.read_bytes() == before
    assert s.EMAIL in pymupdf.open(session.work_path)[0].get_text()


def test_link_over_redacted_url_removed(client):
    url = "https://files.example.com/share?token=abc123def456"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 80), f"Open {url} now", fontsize=11)
    hit = page.search_for(url)[0]
    page.insert_link({"kind": pymupdf.LINK_URI, "from": hit, "uri": url})
    body = scan(client, "links.pdf", doc.tobytes(), "application/pdf")
    r = redact(client, body, [by_category(body)["url"]["id"]])
    assert r.status_code == 200, r.text
    out = pymupdf.open(stream=download(client, r.json()["download_token"]).content, filetype="pdf")
    assert all("token=" not in (link.get("uri") or "") for link in out[0].get_links())
    assert url not in out[0].get_text()


def test_rotated_page_redaction(client):
    body = scan(client, "rotated.pdf", s.make_pdf(LINES, rotate=90), "application/pdf")
    r = redact(client, body, [by_category(body)["email"]["id"]])
    assert r.status_code == 200, r.text
    out = pymupdf.open(stream=download(client, r.json()["download_token"]).content, filetype="pdf")
    assert s.EMAIL not in out[0].get_text()
    assert s.PHONE in out[0].get_text()


def test_comments_removed_from_output(client):
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 80), f"Contact {s.PHONE}", fontsize=11)
    page.add_freetext_annot(pymupdf.Rect(72, 120, 400, 150), f"Reach me at {s.EMAIL}", fontsize=11)
    page.add_text_annot((72, 200), f"Sticky note: {s.EMAIL}")
    body = scan(client, "commented.pdf", doc.tobytes(), "application/pdf")
    assert any("comment" in w for w in body["warnings"])
    r = redact(client, body, [by_category(body)["phone"]["id"]])
    assert r.status_code == 200, r.text
    data = download(client, r.json()["download_token"]).content
    out = pymupdf.open(stream=data, filetype="pdf")
    assert out[0].first_annot is None
    assert s.EMAIL not in out[0].get_text()
    assert s.EMAIL.encode() not in data


def test_form_field_values_scanned_and_redacted(client):
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 80), "Application form", fontsize=11)
    widget = pymupdf.Widget()
    widget.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
    widget.field_name = "contact"
    widget.rect = pymupdf.Rect(72, 200, 400, 220)
    widget.field_value = s.EMAIL
    widget.text_fontsize = 11
    page.add_widget(widget)
    body = scan(client, "form.pdf", doc.tobytes(), "application/pdf")
    email = by_category(body)["email"]
    r = redact(client, body, [email["id"]])
    assert r.status_code == 200, r.text
    data = download(client, r.json()["download_token"]).content
    out = pymupdf.open(stream=data, filetype="pdf")
    assert s.EMAIL not in out[0].get_text()
    assert out[0].first_widget is None
    assert s.EMAIL.encode() not in data
    assert "Application form" in out[0].get_text()


def test_failed_verification_produces_no_file(client, monkeypatch):
    """If the content is not actually removed, Sherlock must refuse to offer a file."""
    body = scan(client, "statement.pdf", s.make_pdf(LINES), "application/pdf")
    monkeypatch.setattr(pymupdf.Page, "apply_redactions", lambda self, **kw: True)
    r = redact(client, body, [by_category(body)["email"]["id"]])
    assert r.status_code == 500
    assert r.json()["error"]["code"] == "redaction_verification_failed"
    session = store.get(body["session_id"])
    assert session.output is None
    assert not any(p.name.startswith("output-") for p in session.workdir.iterdir())


def test_download_token_does_not_reveal_paths(client):
    body = scan(client, "statement.pdf", s.make_pdf(LINES), "application/pdf")
    r = redact(client, body, [by_category(body)["email"]["id"]])
    payload = r.text
    token = r.json()["download_token"]
    session = store.get(body["session_id"])
    assert str(settings.temp_dir) not in payload and str(session.workdir) not in payload
    assert "\\" not in token and "/" not in token and len(token) >= 32
    assert token != body["session_id"]
    d = download(client, token)
    assert d.headers["content-disposition"] == 'attachment; filename="statement-sherlock-redacted.pdf"'
    assert client.get("/api/download/guessed-token-value").status_code == 404
    assert client.get("/api/download/..%2F..%2Fwork.pdf").status_code == 404


def test_redacting_again_replaces_previous_output(client):
    body = scan(client, "statement.pdf", s.make_pdf(LINES), "application/pdf")
    first = redact(client, body, [by_category(body)["email"]["id"]]).json()["download_token"]
    second = redact(client, body, [by_category(body)["pan"]["id"]]).json()["download_token"]
    assert client.get(f"/api/download/{first}").status_code == 404
    assert client.get(f"/api/download/{second}").status_code == 200
    outputs = [p for p in store.get(body["session_id"]).workdir.iterdir() if p.name.startswith("output-")]
    assert len(outputs) == 1


# --------------------------------------------------------------------------
# Images and scanned PDFs (OCR stubbed: see conftest.fake_ocr)
# --------------------------------------------------------------------------

def _ocr_line(*pairs):
    return [Word(text, rect, (1, 1, 1, 1)) for text, rect in pairs]


def test_image_without_server_ocr_awaits_browser_ocr(client, no_ocr):
    body = scan(client, "shot.png", s.make_image(), "image/png")
    assert body["pages"][0]["source"] == "pending"
    assert body["findings"] == []


def _close(a, b, tol):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


@pytest.mark.parametrize("fmt,name,mime", [("PNG", "shot.png", "image/png"), ("JPEG", "photo.jpg", "image/jpeg")])
def test_image_redaction_replaces_pixels(client, fake_ocr, fmt, name, mime):
    fake_ocr["words"] = _ocr_line(("Email:", (20, 40, 80, 60)), (s.EMAIL, (90, 40, 300, 60)))
    exif = Image.Exif()
    exif[0x010E] = "Synthetic description"  # ImageDescription
    data = s.make_image(fmt, exif=exif.tobytes())
    body = scan(client, name, data, mime)
    email = by_category(body)["email"]
    assert email["source"] == "ocr" and email["page"] == 1

    r = redact(client, body, [email["id"]])
    assert r.status_code == 200, r.text
    out_bytes = download(client, r.json()["download_token"]).content
    out = Image.open(io.BytesIO(out_bytes))
    original = Image.open(io.BytesIO(data)).convert("RGB")
    rgb = out.convert("RGB")

    if fmt == "PNG":
        assert out_bytes[1:4] == b"PNG"
        # Every pixel inside the redacted word box is now solid black.
        assert rgb.crop((90, 40, 301, 61)).getextrema() == ((0, 0), (0, 0), (0, 0))
        tol = 0
    else:
        # The original format is preserved; JPEG is lossy, so allow faint
        # compression noise but require the box interior to be dark.
        assert out_bytes[:3] == bytes([0xFF, 0xD8, 0xFF])
        assert r.json()["file_name"].endswith(".jpg")
        assert all(hi <= 64 for _, hi in rgb.crop((94, 44, 297, 57)).getextrema())
        tol = 12
    assert original.crop((94, 44, 297, 57)).getextrema() != rgb.crop((94, 44, 297, 57)).getextrema()
    # Pixels well outside the box are unchanged.
    assert _close(rgb.getpixel((30, 50)), original.getpixel((30, 50)), tol)
    assert _close(rgb.getpixel((350, 150)), original.getpixel((350, 150)), tol)
    # EXIF and text metadata are gone.
    assert "exif" not in out.info and not out.getexif()
    assert b"Synthetic description" not in out_bytes


def test_scanned_pdf_page_is_rasterised(client, fake_ocr):
    # Build a "scanned" PDF: a page containing only an image, no text layer.
    img = Image.new("RGB", (850, 1100), "white")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_image(page.rect, stream=buf.getvalue())
    # OCR runs at settings.ocr_dpi; give boxes in that pixel space.
    k = settings.ocr_dpi / 72
    fake_ocr["words"] = _ocr_line(
        ("Phone", (100 * k, 100 * k, 140 * k, 112 * k)),
        (s.PHONE, (150 * k, 100 * k, 260 * k, 112 * k)),
    )
    body = scan(client, "scan.pdf", doc.tobytes(), "application/pdf")
    assert body["pages"][0]["source"] == "ocr"
    phone = by_category(body)["phone"]
    r = redact(client, body, [phone["id"]])
    assert r.status_code == 200, r.text
    assert any("flattened" in c for c in r.json()["checks"])

    out = pymupdf.open(stream=download(client, r.json()["download_token"]).content, filetype="pdf")
    page = out[0]
    assert page.get_text().strip() == ""
    assert len(page.get_images()) == 1
    pix = page.get_pixmap(dpi=72, clip=pymupdf.Rect(152, 102, 258, 110))
    assert max(pix.samples) < 40  # solid black where the phone number was


def test_scanned_pdf_without_server_ocr_is_pending(client, no_ocr):
    img = Image.new("RGB", (200, 200), "white")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    doc = pymupdf.open()
    doc.new_page().insert_image(pymupdf.Rect(0, 0, 595, 842), stream=buf.getvalue())
    body = scan(client, "scan.pdf", doc.tobytes(), "application/pdf")
    assert body["pages"][0]["source"] == "pending"
