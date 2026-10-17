"""Generate synthetic sample documents for trying Sherlock.

Every value below is invented. The Aadhaar-format number is computed to pass
the checksum but is not a real person's; the AWS key is AWS's own documented
example; 4111 1111 1111 1111 is a published test card number.

Run from the repository root with the backend virtual environment active:

    python sample-files/generate_samples.py
"""

from __future__ import annotations

from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent

LINES = [
    ("Sherlock sample statement (synthetic data)", 15),
    ("", 11),
    ("Customer: Asha Example", 11),
    ("Email: asha.example@example.com", 11),
    ("Mobile: +91 98765 43210", 11),
    ("Office: 022-2345 6789", 11),
    ("PAN: ABCPE1234F", 11),
    ("Aadhaar (sample): 2345 6789 0124", 11),
    ("Account No: 123456789012   IFSC: SBIN0001234", 11),
    ("Card on file: 4111 1111 1111 1111", 11),
    ("", 11),
    ("Shared folder: https://files.example.com/share?token=demo123abc456", 11),
    ("Docs: https://example.com/help", 11),
    ("Deploy key: AKIAIOSFODNN7EXAMPLE", 11),
    ("api_key = demo-1234-abcd-5678", 11),
    ("", 11),
    ("Notes (context that only the AI layer is designed to catch):", 11),
    ("Lives at 42 Lakeview Road, Koramangala, Bengaluru 560034.", 11),
    ("Date of birth: 14/02/1991. The guest Wi-Fi password is sunflower2024.", 11),
    ("Project Falcon acquisition price is confidential: 42 crore.", 11),
    ("", 11),
    ("This statement was generated for testing. The quarterly review is on 12 March 2025.", 11),
]


def make_pdf(path: Path) -> None:
    doc = pymupdf.open()
    page = doc.new_page()
    y = 72
    for text, size in LINES:
        if text:
            page.insert_text((60, y), text, fontsize=size)
        y += size + 9
    doc.set_metadata({"author": "Sherlock Sample Generator", "title": "Synthetic statement"})
    doc.save(path)


def make_png(path: Path) -> None:
    image = Image.new("RGB", (1100, 520), "white")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("arial.ttf", 28)
    except OSError:
        font = ImageFont.load_default(size=28)
    draw.rectangle([0, 0, 1100, 70], fill=(11, 18, 32))
    draw.text((30, 18), "Chat screenshot (synthetic)", fill="white", font=font)
    y = 110
    for line in [
        "Hi! Send the invoice to ravi.sample@example.com",
        "or call me on +91 91234 56789.",
        "My PAN is ABCPE1234F if you need it.",
        "Login link: https://portal.example.com/reset?token=demo987xyz",
    ]:
        draw.text((30, y), line, fill=(15, 23, 42), font=font)
        y += 70
    image.save(path)


def make_scanned_pdf(path: Path, png: Path) -> None:
    """A PDF whose only page is an image (like a scan): no text layer, needs OCR."""
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=282)
    page.insert_image(page.rect, filename=str(png))
    doc.save(path, garbage=3, deflate=True)


if __name__ == "__main__":
    make_pdf(HERE / "synthetic-statement.pdf")
    make_png(HERE / "synthetic-screenshot.png")
    make_scanned_pdf(HERE / "synthetic-scan.pdf", HERE / "synthetic-screenshot.png")
    print("Wrote synthetic-statement.pdf, synthetic-screenshot.png and synthetic-scan.pdf to", HERE)
