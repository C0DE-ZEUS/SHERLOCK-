# Sherlock

**Find the hidden. Protect the personal.**

Sherlock is a privacy-focused web app that scans screenshots, images and PDFs for
sensitive information, lets you review every finding, and produces a new file in which
the content you selected is **permanently removed**, not just covered. It combines
precise rule-based detection with optional context-aware detection by a local AI model
(Qwen3 4B through Ollama). There is no login, no database and no paid API.

```
Upload → Extract text (OCR if needed) → Rules + AI → Review → Confirm → Redact → Download
```

---

## Contents

- [Features](#features)
- [Technology stack](#technology-stack)
- [Architecture](#architecture)
- [Project structure](#project-structure)
- [Windows setup](#windows-setup)
- [Running Sherlock](#running-sherlock)
- [Environment variables](#environment-variables)
- [Testing the AI integration](#testing-the-ai-integration)
- [Automated tests](#automated-tests)
- [Verification checklist](#verification-checklist)
- [Privacy, security and limitations](#privacy-security-and-limitations)
- [Troubleshooting](#troubleshooting)
- [Deploying later](#deploying-later)
- [Opening the ZIP on Windows](#opening-the-zip-on-windows)

---

## Features

**Detection: two complementary layers**

| Layer | What it finds | How |
| --- | --- | --- |
| Rules (always on) | Emails, phone numbers (Indian and international), URLs with tokens or keys, Aadhaar-format numbers (Verhoeff checksum), PAN, bank account numbers (only next to an account label), IFSC codes, payment cards (Luhn), API keys, private keys, JWTs, labelled passwords | Regex plus validation |
| AI (optional) | Names, dates of birth, postal addresses, passwords written in sentences, salaries and prices, confidential business details, other sensitive personal details | Qwen3 4B through Ollama, structured JSON output |

- Identity matches are labelled **"Possible …"**. Sherlock checks formats and checksums but never verifies who a number belongs to.
- AI findings are **suggestions**. They start unselected, carry a confidence score and a short reason, and are badged as *AI suggestion*.
- Before text is sent to the model, everything the rules already found is blanked out with `#`. So emails, card numbers and keys are **never sent to the AI**, and the model spends its time only on what rules miss. (In testing this cut AI time on the sample from 142 s to 48 s.)
- The model's suggestions are matched **verbatim** against the extracted text. Their position on the page always comes from real PDF or OCR word boxes, never from the model. Suggestions that don't appear in the document are discarded as invented.

**OCR**

- Digital PDFs: the text layer is read directly with PyMuPDF.
- Images and scanned pages: OCR with **Tesseract on the server** if it is installed, otherwise **in your browser with Tesseract.js**. The browser engine and its English model are served by Sherlock itself (no CDN), so **visitors never need to install anything**.

**Review**

- A processing tracker shows real status for text extraction, OCR, rules and AI, including AI progress and elapsed time.
- A results dashboard shows totals, high-risk count, rule versus AI counts, and categories.
- The findings panel shows masked values (with an optional reveal), risk badges (text plus dots, not colour alone), source badges, explanations, filters (All / Rules / AI) and bulk selection.
- The document preview shows planned redactions as solid boxes (which hide the values) and unselected findings as dashed outlines.
- A confirmation dialog summarises what will be removed. Nothing is redacted without it.

**Redaction**

- PDF: PyMuPDF `apply_redactions()` **deletes the characters** from the page content and blanks image pixels under each box. Links over redacted areas, comments and annotations, metadata, XMP, bookmarks, attachments and scripts are removed. Scanned pages with redactions are re-rendered as a single new image.
- Images: pixels inside each box are overwritten. PNG stays PNG and JPG stays JPG, with EXIF, ICC and text metadata removed.
- **Verified before download.** The output is re-opened and checked. Every selected occurrence must no longer be extractable, no text may remain inside any redaction box, metadata must be gone, and redacted pixels must be black. If any check fails, no file is offered.

## Technology stack

| Part | Technology |
| --- | --- |
| Frontend | React 18, TypeScript, Vite 5, Tailwind CSS 3, Inter (self-hosted), Tesseract.js 5 |
| Backend | Python 3.11+ (tested on 3.13), FastAPI, Uvicorn, Pydantic 2, PyMuPDF, Pillow, pytesseract, httpx |
| AI | Ollama + `qwen3:4b` (local), or any OpenAI-compatible server (optional, explicit configuration) |
| Tests | pytest, Vitest, Testing Library |
| Deployment prep | Dockerfile (single container), Render blueprint, see [DEPLOYMENT.md](DEPLOYMENT.md) |

## Architecture

```
Browser (React)                              FastAPI backend                       Optional
───────────────                              ───────────────                       ────────
upload ───────────── POST /api/scan ───────▶ validate (type, MIME, magic bytes, size)
                                              extract text + word boxes (PyMuPDF / Tesseract)
                                              rule detection ─▶ session (in memory + temp folder)
      ◀──────────── findings (masked) ───────┘
if pages are "pending" (no server OCR):
  GET  /ocr-image/{page} ─▶ page image
  Tesseract.js in the browser ─▶ words + boxes
  POST /ocr ─────────────────────────────────▶ validate boxes, run rules
if AI is on and available:
  POST /ai ──────────────────────────────────▶ background job (1 at a time)
  GET  /ai (poll every 3 s) ◀── progress ────   mask rule findings ─▶ chunk text ─▶ Ollama /api/chat
                                                ◀── JSON ─ validate ─ match verbatim ─ dedupe ─ merge
review + confirm
  POST /api/redact {ids} ────────────────────▶ redact with server-side boxes ─▶ verify ─▶ token
  GET  /api/download/{token} ◀──────────────── sanitized file
  DELETE /api/session/{id} ──────────────────▶ temp folder deleted
```

**Design notes**

- The browser only ever sends finding IDs. Redaction uses the server's own stored coordinates.
- AI runs as a **background job** because a 4B model on a laptop CPU takes about 30–90 s per chunk. The rule findings are reviewable straight away.
- AI providers sit behind a small interface (`backend/app/services/ai/providers.py`): `ollama`, `openai_compatible` or `none`. Nothing falls back to another provider silently.
- OCR, rule detection, AI detection and redaction are separate modules with their own tests.

## Project structure

```
sherlock/
├─ backend/
│  ├─ app/
│  │  ├─ main.py               app, CORS, security headers (CSP), errors, startup cleanup
│  │  ├─ config.py             settings from environment variables (load_settings)
│  │  ├─ static_site.py        serves the built frontend in single-URL deployments
│  │  ├─ api/routes.py         HTTP endpoints
│  │  ├─ schemas/models.py     request/response models
│  │  └─ services/
│  │     ├─ file_security.py   upload validation, safe names, temp cleanup
│  │     ├─ text_extraction.py PDF text + server OCR with word boxes
│  │     ├─ client_ocr.py      validates browser OCR results
│  │     ├─ detection.py       rule detectors, validators, masking
│  │     ├─ scanner.py         scan pipeline
│  │     ├─ sessions.py        in-memory sessions, tokens, expiry
│  │     ├─ redaction.py       redaction + verification
│  │     ├─ previews.py        page previews
│  │     ├─ limits.py          rate limit + concurrency cap
│  │     └─ ai/
│  │        ├─ providers.py    Ollama / OpenAI-compatible / disabled
│  │        ├─ detector.py     prompt, JSON schema, validation, chunking, span matching
│  │        └─ jobs.py         background jobs, masking, merge + dedupe
│  ├─ tests/                   pytest suite (synthetic data only)
│  ├─ requirements.txt, requirements-dev.txt, .env.example
├─ frontend/
│  ├─ src/
│  │  ├─ App.tsx               workflow: upload → scan → OCR → AI → review → redact
│  │  ├─ pages/                UploadPage (landing), ReviewPage, DonePage
│  │  ├─ components/           Navbar, Dropzone, ProcessingPanel, ResultsSummary,
│  │  │                        FindingsList, DocumentPreview, ConfirmDialog, Toggle, ...
│  │  ├─ services/             api.ts, ocr.ts (Tesseract.js), stages.ts, validation.ts
│  │  └─ test/                 Vitest tests
│  ├─ scripts/copy-ocr-assets.mjs   copies Tesseract.js files into public/ocr
│  ├─ package.json, vite.config.ts, tailwind.config.js, .env.example
├─ sample-files/               synthetic samples + generator
├─ Dockerfile, .dockerignore, render.yaml
├─ README.md, DEPLOYMENT.md, .gitignore
```

## Windows setup

You need **Python 3.11+** and **Node.js 18+**. Ollama is optional (for AI); Tesseract is optional (the browser can do OCR).

1. Install **Python** from <https://www.python.org/downloads/> and tick *"Add python.exe to PATH"*.
2. Install **Node.js LTS** from <https://nodejs.org/>.
3. **Ollama (for AI detection):** install it from <https://ollama.com/download>, then download the model (about 2.5 GB):

   ```powershell
   ollama pull qwen3:4b
   ```

   Check it with `ollama list`. Ollama listens on `http://localhost:11434`, and Sherlock uses `/api/chat`.
4. **Tesseract (optional, faster OCR for images):** run `winget install --id UB-Mannheim.TesseractOCR`, or use the installer from <https://github.com/UB-Mannheim/tesseract/wiki>. Sherlock finds it in `C:\Program Files\Tesseract-OCR` automatically. Without it, OCR runs in the browser.

Install the dependencies once (PowerShell, from the `sherlock` folder):

```powershell
cd backend
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
cd ..\frontend
npm install
```

## Running Sherlock

Use **two terminals**.

**Terminal 1: backend**

```powershell
cd sherlock\backend
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**Terminal 2: frontend**

```powershell
cd sherlock\frontend
npm run dev
```

Open **<http://localhost:5173>**. Make sure Ollama is running (it usually starts with Windows; otherwise open the Ollama app) if you want AI detection.

To use a configuration file, copy `backend\.env.example` to `backend\.env`, edit it, and add `--env-file .env` to the backend command.

**Production-style single URL (optional):** build the frontend and let the backend serve it.

```powershell
cd sherlock\frontend
npm run build
cd ..\backend
$env:SHERLOCK_STATIC_DIR = "..\frontend\dist"
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Then open <http://127.0.0.1:8000>.

## Environment variables

All are optional. The full list with comments is in [`backend/.env.example`](backend/.env.example) and [`frontend/.env.example`](frontend/.env.example).

| Variable | Default | Purpose |
| --- | --- | --- |
| `SHERLOCK_AI_PROVIDER` | `ollama` | `ollama`, `openai_compatible` or `none` |
| `SHERLOCK_AI_BASE_URL` | `http://localhost:11434` | Model server URL |
| `SHERLOCK_AI_MODEL` | `qwen3:4b` | Model name |
| `SHERLOCK_AI_API_KEY` | (empty) | Only for OpenAI-compatible servers that need one |
| `SHERLOCK_AI_TIMEOUT_SECONDS` | `180` | Per model call |
| `SHERLOCK_AI_MAX_CHARS` / `SHERLOCK_AI_CHUNK_CHARS` | `6000` / `2000` | Text budget per scan and per call |
| `SHERLOCK_TESSERACT_CMD` | auto-detect | Path to `tesseract.exe` |
| `SHERLOCK_OCR_LANG` | `eng` | Tesseract language(s) |
| `SHERLOCK_MAX_UPLOAD_MB` / `SHERLOCK_MAX_PDF_PAGES` | `10` / `30` | Upload limits |
| `SHERLOCK_SESSION_TTL_MINUTES` | `30` | Idle time before a scan's files are deleted |
| `SHERLOCK_RATE_LIMIT` / `SHERLOCK_MAX_CONCURRENT_JOBS` | `30` / `2` | Abuse protection |
| `SHERLOCK_DEPLOYMENT` | `local` | `hosted` changes privacy wording and hides `/docs` |
| `SHERLOCK_ALLOWED_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | CORS allow-list |
| `SHERLOCK_STATIC_DIR` | (unset) | Serve a built frontend |
| `VITE_API_BASE` (frontend) | (empty = same origin) | API URL when frontend and backend are on different domains |
| `VITE_GITHUB_URL` (frontend) | (empty = hidden) | Footer GitHub link |

## Testing the AI integration

1. Confirm Ollama and the model are ready:

   ```powershell
   ollama list
   curl.exe http://127.0.0.1:8000/api/health
   ```

   The `ai` block should show `"available": true` and `"model": "qwen3:4b"`. The navbar chip shows **AI · qwen3:4b**.
2. Upload `sample-files\synthetic-statement.pdf` with the AI toggle on.
3. The 12 rule findings appear in about a second. The **AI analysis** card then shows progress and elapsed time.
4. When it finishes (about 50 s on an i9-13900H CPU in our test), you should see AI suggestions such as the customer name, the two-line address, the date of birth, the Wi-Fi password and the deal price. Results can vary between runs, because the model is not perfectly consistent.
5. Turn the toggle off, or stop Ollama, and scan again: the AI card says *Off* or *unavailable*, while rules, review and redaction keep working.

**Speed on your laptop (i9-13900H, 16 GB, Iris Xe):** Ollama typically runs Qwen3 4B on the CPU on this kind of laptop (we measured about 7 tokens/s), which is much slower than a dedicated GPU. Sherlock keeps this practical by:

- running one AI job at a time
- turning off Qwen3's "thinking" mode
- capping input at 6,000 characters in 2,000-character chunks
- masking known findings
- sending identical chunks only once
- never re-running a finished job

Close other heavy apps if it is slow. Expect roughly 30–90 s per chunk.

## Automated tests

```powershell
cd sherlock\backend
.venv\Scripts\python.exe -m pytest -q

cd ..\frontend
npm test
npm run build
```

**Backend (102 tests)** covers:

- rule detection and false positives
- upload validation (wrong type, disguised file, MIME mismatch, oversized, empty, corrupt, password-protected, path traversal)
- PDF text removal, unselected text kept, metadata, links, comments, form fields, rotated pages, overlapping redactions, multi-line findings
- the verification safety net
- image pixel replacement for PNG and JPG
- scanned-PDF rasterisation
- browser-OCR submission validation
- real Tesseract OCR (skipped automatically if Tesseract isn't installed)
- the AI layer: JSON parsing, malformed, empty and invented output, chunking, timeouts, unreachable model, the providers with mocked HTTP, background jobs, masking, dedupe, opt-in suggestions, and no document text in logs
- configuration from environment variables, deployment files, static serving, rate limits, and temp-file cleanup

**Frontend (23 tests)** covers:

- landing page, AI toggle states and wording
- loading, empty, error and success states
- browser OCR flow and AI polling flow
- filters and selection
- the confirm dialog
- redaction requests, download and start over
- the stage logic

Tests never call a real AI model; a fake provider stands in. The real Qwen3 integration was verified manually, as described above.

## Verification checklist

- [ ] `GET /api/health` returns `"status": "ok"`, with AI and OCR shown as expected.
- [ ] Upload `synthetic-statement.pdf`: 12 rule findings, masked by default; *Reveal* shows one value.
- [ ] AI card runs and finishes, and AI suggestions appear unselected with an *AI suggestion* badge.
- [ ] Toggle a few findings and check that the preview boxes switch between solid and dashed.
- [ ] *Review & redact* opens a dialog listing the counts; *Go back* and the Escape key cancel it.
- [ ] Confirm, then download: open the PDF, try to select or copy the redacted areas (nothing comes out), and confirm unselected text is still there.
- [ ] Upload `synthetic-screenshot.png` (OCR) and `synthetic-scan.pdf` (scanned page), redact, and check the output.
- [ ] *Start over*: the download link stops working (404).
- [ ] Upload a `.txt` file, a file over 10 MB, and a password-protected PDF, and check each gives a clear error.

## Privacy, security and limitations

**What is protected**

- Files go only to the Sherlock backend. Text goes to an AI model only if one is configured; with local Ollama it never leaves your machine. The UI says where text is sent before you enable AI.
- No permanent storage. The uploaded bytes are never written to disk; only a working copy and the output are kept, in a random temp folder. These are deleted on Start over, on tab close (best effort), after the TTL, and at every startup.
- Logs contain event names and counts only, never document text or values; a test checks this. The Docker image disables access logs, because URLs contain session tokens.
- Uploads must match on extension, MIME type and magic bytes. Size, page count, pixel count and OCR word count are capped. Rate limits and a concurrency cap bound resource use.
- Strict security headers: CSP `default-src 'self'` with no third-party sources, `nosniff`, `no-referrer`, `frame-ancestors 'none'`. CORS is limited to configured origins.
- AI output is untrusted. It is schema-validated, must match the document verbatim, starts unselected, and the document is wrapped as data in the prompt to blunt prompt-injection.

**Limitations (please read)**

- **Detection can miss things.** That includes handwriting, signatures, faces, photos of ID cards, unusual formats, and text the AI misunderstands. A 4B model makes mistakes in both directions. Always check the output yourself.
- AI analysis covers at most the first 6,000 characters by default (the UI says when it was truncated).
- Images embedded inside otherwise-digital PDFs are not OCR'd.
- Whole words are redacted, so a match inside a longer word removes the whole word.
- Comments and annotations are removed from PDF output rather than scanned. Scanned pages with redactions lose any hidden text layer.
- Sessions live in memory: restarting the backend clears scans. This is not built for multi-server scaling.
- This is a portfolio project. It has been tested as described above but **not independently security-audited**. Don't rely on it for legal or compliance-grade sanitisation.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| "Sherlock can't reach its backend" | Start terminal 1 (port 8000) and reload. |
| AI chip says *AI unavailable* | Start Ollama, run `ollama pull qwen3:4b`, then reload after about 15 s (the status is cached briefly). |
| AI is very slow or times out | Expected on CPU. Close heavy apps, lower `SHERLOCK_AI_MAX_CHARS`, or raise `SHERLOCK_AI_TIMEOUT_SECONDS`. Rule findings stay usable meanwhile. |
| First browser OCR takes a while | The ~11 MB OCR engine and English model load once, then the browser caches them. |
| `npm run dev` fails with "missing … tesseract" | Run `npm install` again; the OCR assets are copied from `node_modules`. |
| Port already in use | Stop the other process, or use `--port 8001` and update the proxy target in `vite.config.ts`. |
| `pip install` fails on PyMuPDF | Use 64-bit Python 3.11–3.13 and upgrade pip first. |
| Redaction says it could not confirm removal | The safety check refused to produce an unverified file. Try again; if it repeats, print the PDF to a new PDF and retry. |

## Deploying later

Sherlock is **not deployed**. [DEPLOYMENT.md](DEPLOYMENT.md) covers:

- hosting options and their costs
- build and start commands
- environment variables and CORS
- how to add a hosted AI model later (a public site can't use the Ollama on your laptop, and must never try to)
- a pre-launch security checklist

## Opening the ZIP on Windows

1. Right-click `sherlock-project.zip`, choose **Extract All…**, pick a folder (for example `Documents\Projects`) and click **Extract**.
2. Open VS Code, choose **File → Open Folder…**, and select the extracted `sherlock` folder.
3. Open a terminal with **Terminal → New Terminal** and follow [Windows setup](#windows-setup). The ZIP has no `node_modules` or `.venv`, so the install step is required (it takes a few minutes).
4. Run the two terminals from [Running Sherlock](#running-sherlock).
