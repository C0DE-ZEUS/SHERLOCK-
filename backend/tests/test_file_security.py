import time

import pymupdf
import pytest

from app.config import settings
from app.errors import SherlockError
from app.services.file_security import clean_temp_root, safe_display_stem, validate_upload
from app.services.sessions import store
from tests import synthetic as s


def code_of(client, name, data, mime):
    r = client.post("/api/scan", files={"file": (name, data, mime)})
    return r.status_code, r.json()["error"]["code"]


def test_rejects_unsupported_extension(client):
    assert code_of(client, "notes.txt", b"hello", "text/plain") == (415, "unsupported_file_type")
    assert code_of(client, "tool.exe", b"MZ\x90\x00", "application/octet-stream") == (415, "unsupported_file_type")


def test_rejects_disguised_file(client):
    # An executable renamed to .pdf fails the signature check.
    assert code_of(client, "invoice.pdf", b"MZ\x90\x00" * 100, "application/pdf") == (415, "signature_mismatch")
    # A PNG renamed to .jpg is also rejected.
    assert code_of(client, "photo.jpg", s.make_image("PNG"), "image/jpeg") == (415, "signature_mismatch")


def test_rejects_mime_mismatch(client):
    pdf = s.make_pdf(["hello"])
    assert code_of(client, "doc.pdf", pdf, "image/png") == (415, "unsupported_file_type")


def test_rejects_oversized_file(client):
    big = b"%PDF-1.7\n" + b"0" * (settings.max_upload_bytes + 10)
    assert code_of(client, "big.pdf", big, "application/pdf") == (413, "file_too_large")


def test_rejects_empty_and_missing(client):
    assert code_of(client, "empty.pdf", b"", "application/pdf") == (400, "empty_file")
    r = client.post("/api/scan")
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_request"


def test_rejects_corrupt_pdf(client):
    assert code_of(client, "bad.pdf", b"%PDF-1.7\nthis is not really a pdf", "application/pdf")[1] == "corrupt_file"


def test_rejects_password_protected_pdf(client):
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "secret")
    data = doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner-pass", user_pw="user-pass")
    assert code_of(client, "locked.pdf", data, "application/pdf") == (422, "password_protected")


def test_filename_never_used_as_path():
    assert safe_display_stem("../../etc/passwd") == "passwd"
    assert safe_display_stem("..\\..\\Windows\\system32\\evil.pdf") == "evil"
    assert safe_display_stem("my report (final).pdf") == "my-report-final"
    assert safe_display_stem("") == "document"
    upload = validate_upload("../../x.PDF", "application/pdf", s.make_pdf(["hi"]))
    assert upload.extension == ".pdf" and "/" not in upload.display_stem


def test_generic_mime_still_needs_signature():
    with pytest.raises(SherlockError):
        validate_upload("a.png", "application/octet-stream", b"not a png")


def test_scan_does_not_store_original_upload(client):
    r = client.post("/api/scan", files={"file": ("doc.pdf", s.make_pdf([s.EMAIL]), "application/pdf")})
    session = store.get(r.json()["session_id"])
    assert sorted(p.name for p in session.workdir.iterdir()) == ["work.pdf"]


def test_reset_deletes_session_files(client):
    r = client.post("/api/scan", files={"file": ("doc.pdf", s.make_pdf([s.EMAIL]), "application/pdf")})
    body = r.json()
    session = store.get(body["session_id"])
    red = client.post("/api/redact", json={"session_id": body["session_id"], "finding_ids": [body["findings"][0]["id"]]})
    token = red.json()["download_token"]
    workdir = session.workdir
    assert workdir.exists()

    assert client.delete(f"/api/session/{body['session_id']}").status_code == 204
    assert not workdir.exists()
    assert client.get(f"/api/download/{token}").status_code == 404
    assert client.get(f"/api/session/{body['session_id']}/preview/1").status_code == 404


def test_expired_sessions_are_cleaned(client):
    r = client.post("/api/scan", files={"file": ("doc.pdf", s.make_pdf([s.EMAIL]), "application/pdf")})
    session = store.get(r.json()["session_id"])
    session.last_access = time.time() - settings.session_ttl_seconds - 5
    store.expire()
    assert not session.workdir.exists()
    assert len(store) == 0


def test_stale_temp_folders_removed_on_startup():
    stale = settings.temp_dir / ("ab" * 16)  # named like a Sherlock session folder
    stale.mkdir(parents=True, exist_ok=True)
    (stale / "work.pdf").write_bytes(b"x")
    unrelated = settings.temp_dir / "not-sherlock"
    unrelated.mkdir(exist_ok=True)
    (settings.temp_dir / "notes.txt").write_text("keep me")

    assert clean_temp_root() >= 1
    assert not stale.exists()
    # Anything Sherlock did not create is left alone.
    assert unrelated.exists() and (settings.temp_dir / "notes.txt").exists()
