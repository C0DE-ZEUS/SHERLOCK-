# Sample files

Everything in this folder is **synthetic**. No real person's data is included,
and you should never commit real documents here.

| File | What it contains | Shows |
| --- | --- | --- |
| `synthetic-statement.pdf` | Text-based PDF: email, Indian mobile and landline, PAN-format code, Aadhaar-format number (checksum-valid but invented), account number + IFSC, the published test card `4111 1111 1111 1111`, a link with `token=`, AWS's documented example key ID, a labelled `api_key`, plus a "Notes" block with a name, a two-line address, a date of birth, a password inside a sentence and a confidential deal price | 12 rule findings; the notes are what the AI layer is designed to catch |
| `synthetic-screenshot.png` | Fake chat screenshot: email, phone, PAN-format code, reset link with a token | OCR (server Tesseract or in-browser Tesseract.js) |
| `synthetic-scan.pdf` | The screenshot embedded as an image-only PDF page (no text layer) | Scanned-PDF OCR and page rasterisation on redaction |

Regenerate them (backend virtual environment, from the project root):

```powershell
backend\.venv\Scripts\python.exe sample-files\generate_samples.py
```

## Making your own test documents

- Use `example.com` / `example.org` emails and obviously fake names.
- Use placeholder numbers such as `+91 98765 43210`.
- For an Aadhaar-format number, compute a Verhoeff check digit for 11 made-up digits
  (see `backend/tests/synthetic.py`). Never use a real one.
- For cards, use published test numbers such as `4111 1111 1111 1111`.
- For secrets, use vendor-documented example keys (e.g. `AKIAIOSFODNN7EXAMPLE`).
