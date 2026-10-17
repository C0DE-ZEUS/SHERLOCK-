"""Synthetic test data. Nothing here belongs to a real person.

Secret-like strings are assembled at runtime so this file never contains a
literal that resembles a real credential (which would also trip GitHub's
secret scanning on push).
"""

from __future__ import annotations

import io

import pymupdf
from PIL import Image

from app.services.detection import _VERHOEFF_D, _VERHOEFF_P

_VERHOEFF_INV = [0, 4, 3, 2, 1, 5, 6, 7, 8, 9]


def verhoeff_digit(number: str) -> str:
    c = 0
    for i, ch in enumerate(reversed(number)):
        c = _VERHOEFF_D[c][_VERHOEFF_P[(i + 1) % 8][int(ch)]]
    return str(_VERHOEFF_INV[c])


def aadhaar_like(prefix11: str = "23456789012") -> str:
    """A 12-digit Aadhaar-format number with a valid checksum, spaced 4-4-4."""
    digits = prefix11 + verhoeff_digit(prefix11)
    return f"{digits[:4]} {digits[4:8]} {digits[8:]}"


EMAIL = "jane.doe@example.com"
PHONE = "+91 98765 43210"
PAN = "ABCPE1234F"
IFSC = "SBIN0001234"
ACCOUNT = "123456789012"
TEST_CARD = "4111 1111 1111 1111"  # a published test card number
GITHUB_TOKEN = "gh" + "p_" + "A1b2C3d4E5" * 4
AWS_KEY = "AKIA" + "IOSFODNN7" + "EXAMPLE"  # AWS's documented example key ID


def make_pdf(lines: list[str], *, metadata: dict | None = None, rotate: int = 0) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    for i, line in enumerate(lines):
        page.insert_text((72, 80 + 22 * i), line, fontsize=11)
    if rotate:
        page.set_rotation(rotate)
    if metadata:
        doc.set_metadata(metadata)
    return doc.tobytes()


def make_image(fmt: str = "PNG", size=(400, 200), color=(255, 255, 255), exif: bytes | None = None) -> bytes:
    image = Image.new("RGB", size, color)
    # Put some non-white content where the stub OCR "finds" words.
    for x in range(20, 380):
        for y in range(40, 60):
            image.putpixel((x, y), (30, 30, 200))
    buf = io.BytesIO()
    kwargs = {"exif": exif} if exif else {}
    image.save(buf, fmt, **kwargs)
    return buf.getvalue()
