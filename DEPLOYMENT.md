# Deploying Sherlock (later)

> **Status: not deployed.** Nothing in this project creates cloud resources or
> accounts. This guide is for when you decide to publish Sherlock at a public
> HTTPS URL. Provider details reflect what was known when this was written
> (late 2026). **Always check current pricing and limits before you sign up.**

---

## 1. What a public deployment looks like

```
Visitor's browser ──HTTPS──▶ one container (Dockerfile)
                              ├─ FastAPI backend (/api/*)
                              ├─ built React frontend (served as static files)
                              ├─ Tesseract OCR (installed in the image)
                              └─ AI: OFF by default (SHERLOCK_AI_PROVIDER=none)
```

- **One container, one URL.** The backend serves the built frontend, so there is no CORS to configure and no API URL to set.
- **Visitors install nothing.** OCR runs on the server (Tesseract is in the image) or, as a fallback, in the visitor's browser (Tesseract.js, served from the same site).
- **Rule detection, review, redaction and download work without any AI.**
- **AI is off on public deployments by default.** Your local Ollama only works on your laptop: a public site can't reach it, and you must **never expose port 11434 to the internet** (Ollama has no authentication). When AI is not configured, the UI says *AI disabled on this server* and never claims AI ran.

## 2. Pre-built configuration in this repository

| File | Purpose |
| --- | --- |
| `Dockerfile` | Multi-stage build: Node builds the frontend, then a Python 3.12 slim image with Tesseract (eng) runs Uvicorn as a non-root user. Sets `SHERLOCK_DEPLOYMENT=hosted`, `SHERLOCK_AI_PROVIDER=none`, a 15-minute session TTL, a health check, `--proxy-headers` (so the rate limiter sees real client IPs) and `--no-access-log` (request URLs contain session tokens). |
| `.dockerignore` | Keeps `node_modules`, `.venv`, tests, samples, `.env` and ZIPs out of the image. |
| `render.yaml` | Render Blueprint for a single free Docker web service with `/api/health` checks. |
| `backend/.env.example`, `frontend/.env.example` | Every setting, with safe placeholder values. |

### Build and run the image locally first

Requires Docker Desktop to be running.

```powershell
cd sherlock
docker build -t sherlock .
docker run --rm -p 8000:8000 sherlock
```

Open <http://localhost:8000> and run the checks in section 7.

> The Docker image was **not** built during development: the configuration is covered by automated tests, but Docker Desktop was not running. Run the commands above once before your first deployment.

### Without Docker (any Python host)

```bash
# build the frontend
cd frontend && npm ci && npm run build
# install and start the backend, serving the built frontend
cd ../backend && pip install -r requirements.txt
SHERLOCK_DEPLOYMENT=hosted SHERLOCK_STATIC_DIR=../frontend/dist SHERLOCK_AI_PROVIDER=none \
  uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips='*' --no-access-log
```

Server-side OCR also needs the `tesseract-ocr` system package. Without it, the browser does the OCR.

## 3. Hosting options

Sherlock needs a host that runs a **Docker container or Python process with
~512 MB+ RAM** (PyMuPDF and OCR are memory-hungry on large pages). Pure static hosts
(GitHub Pages, Netlify, Vercel static) **cannot** run the backend.

| Option | Fit | Notes (verify current terms) |
| --- | --- | --- |
| **Render** (Docker web service) | Simplest: `render.yaml` included | The free instance type has had about 512 MB RAM and sleeps after ~15 min idle (the first request then takes ~30–60 s). Paid instances remove sleep. |
| **Hugging Face Spaces** (Docker SDK) | Good free CPU resources | Free CPU Spaces have offered 2 vCPU and 16 GB RAM, but sleep after inactivity and are public by default. Needs a Space-specific README header (`sdk: docker`, `app_port: 8000`). |
| **Koyeb / Railway / Fly.io** | Docker-based PaaS | Free allowances change often; several now offer only trial credits. Check before choosing. |
| **A small VPS** (e.g. 1–2 GB RAM) | Full control | Typically a few USD/month. You manage HTTPS (e.g. Caddy), updates and firewalling. |

**Split frontend/backend (optional):** you can host `frontend/dist` on a static host and the backend elsewhere. In that case:

1. Build the frontend with `VITE_API_BASE=https://your-api.example.com`.
2. Set `SHERLOCK_ALLOWED_ORIGINS=https://your-frontend.example.com` on the backend (comma-separated, no trailing slash).
3. Serve the frontend with an equivalent Content-Security-Policy: `script-src 'self' 'wasm-unsafe-eval'; worker-src 'self'; connect-src 'self' data: https://your-api.example.com`.

The single-container setup avoids all of this and is recommended.

### Render, step by step (when you're ready)

1. Push the repository to GitHub (without any `.env` file).
2. In Render: **New → Blueprint**, then select the repository. Render reads `render.yaml`.
3. Wait for the build, then open the `onrender.com` URL and run section 7.
4. Optional: add a custom domain. Render provides HTTPS certificates.

## 4. Environment variables for production

| Variable | Recommended value | Why |
| --- | --- | --- |
| `SHERLOCK_DEPLOYMENT` | `hosted` (set in Dockerfile) | Correct privacy wording; hides `/docs` and `/openapi.json` |
| `SHERLOCK_AI_PROVIDER` | `none` (set in Dockerfile) | No model available unless you add one (section 5) |
| `SHERLOCK_SESSION_TTL_MINUTES` | `15` (set in Dockerfile) | Shorter retention of temporary files |
| `SHERLOCK_MAX_UPLOAD_MB` | `10` | Bound memory and CPU |
| `SHERLOCK_MAX_PDF_PAGES` | `30` (lower to `10` on 512 MB instances) | Bound memory |
| `SHERLOCK_RATE_LIMIT` | `30` per IP per 10 min (or lower) | Abuse protection |
| `SHERLOCK_MAX_CONCURRENT_JOBS` | `1`–`2` on small instances | Avoid running out of memory |
| `SHERLOCK_ALLOWED_ORIGINS` | your exact frontend origin(s) | Only needed for split hosting |
| `PORT` | provided by the host | Uvicorn listens on it |

Never commit secrets. If you add an AI API key, set it in the host's secret settings, not in the repository.

## 5. Adding AI to a public deployment (future)

The public site cannot use your laptop. Options, in order of privacy:

1. **Self-hosted model server you control.** Run Ollama, llama.cpp server or vLLM on a machine with a GPU, reachable **only from the Sherlock backend** over a private network (never open to the internet). Then set:

   ```
   SHERLOCK_AI_PROVIDER=ollama              # or openai_compatible for vLLM/llama.cpp
   SHERLOCK_AI_BASE_URL=http://10.0.0.5:11434   # private address
   SHERLOCK_AI_MODEL=qwen3:4b
   ```

   *Cost:* GPU instances are typically billed hourly and are the most expensive option to keep running 24/7.
2. **Hosted inference API (OpenAI-compatible).** Set `SHERLOCK_AI_PROVIDER=openai_compatible`, `SHERLOCK_AI_BASE_URL=https://provider.example/v1`, `SHERLOCK_AI_MODEL=...` and `SHERLOCK_AI_API_KEY` (as a secret).
   *Cost:* usually **per token**. Every scan sends up to `SHERLOCK_AI_MAX_CHARS` characters (default 6,000, about 1,500 tokens) plus the response. Estimate monthly scans × tokens × price, and set a spending limit with the provider.
   *Privacy:* document text then goes to a third party. Sherlock's UI automatically states the host it is sent to before the visitor enables AI, and rule-detected values are masked out before sending. Check the provider's data-retention terms, and update your privacy wording if needed.

Sherlock never switches providers silently and never reports AI as successful when it wasn't. If the configured provider is unreachable, the AI card shows *unavailable*, and rules, review and redaction keep working.

## 6. Security checklist before publishing

- [ ] `SHERLOCK_DEPLOYMENT=hosted` and the app shows the hosted privacy wording.
- [ ] `/docs` and `/openapi.json` return 404 in production.
- [ ] Ollama or any model server is **not** reachable from the internet.
- [ ] No `.env` or secrets in the repository (`git status` shows none; `.gitignore` covers `.env`).
- [ ] HTTPS only (the host's TLS); custom domains have certificates.
- [ ] Response headers include the Content-Security-Policy, `X-Content-Type-Options: nosniff` and `X-Frame-Options: DENY` (check with browser dev tools).
- [ ] Access logs are disabled (`--no-access-log`) or scrubbed of `/api/session/...` and `/api/download/...` URLs.
- [ ] Rate limit and concurrency are set for your instance size, and the upload limit is tested.
- [ ] You have written a short privacy notice for your site (what is processed, retention, and the AI provider if any).
- [ ] You understand this is a portfolio project that has **not** had an independent security audit.

## 7. Post-deployment verification

1. `https://<your-url>/api/health` returns `"status":"ok"`, `"deployment":"hosted"`, and the AI and OCR state you expect.
2. Upload `sample-files/synthetic-statement.pdf`: findings appear; redact and download; the redacted text can't be copied from the PDF.
3. Upload `sample-files/synthetic-screenshot.png`: OCR works (server, or *OCR · browser* in the navbar); redact and download.
4. Upload a `.txt` file and an 11 MB file: clear errors.
5. *Start over*, then the old download URL returns 404.
6. Browser console: no CSP errors. Network tab: no requests to third-party domains.
7. Leave the site idle past the TTL and confirm old download links stop working.

## 8. Costs and limits to expect

| Item | Free path | When it costs money |
| --- | --- | --- |
| Hosting | Free tiers (with sleep and RAM limits) | Always-on or more-RAM instances, typically a few to tens of USD/month |
| Domain | Host subdomain (e.g. `*.onrender.com`) | Custom domain, typically ~10–20 USD/year |
| OCR | Included (Tesseract / Tesseract.js) | Never, just CPU time |
| AI | Off by default | GPU server (hourly) or per-token API usage |
| Bandwidth | Usually generous on free tiers | Heavy traffic; the OCR assets are ~11 MB per first-time visitor using browser OCR |

Free tiers can change or be withdrawn. Set billing alerts wherever a payment method is attached.
