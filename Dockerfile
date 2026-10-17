# Sherlock: one container serving the API, the built frontend, and Tesseract OCR.
# AI detection is off by default here: a public server cannot (and must not)
# reach a model on a developer's laptop. See DEPLOYMENT.md to add a hosted model.
# Build:  docker build -t sherlock .
# Run:    docker run --rm -p 8000:8000 sherlock   ->  http://localhost:8000

# ---- 1. Build the React frontend -------------------------------------------
FROM node:22-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- 2. Python runtime with Tesseract ---------------------------------------
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    SHERLOCK_DEPLOYMENT=hosted \
    SHERLOCK_STATIC_DIR=/app/static \
    SHERLOCK_TEMP_DIR=/tmp/sherlock-work \
    SHERLOCK_SESSION_TTL_MINUTES=15 \
    SHERLOCK_AI_PROVIDER=none \
    PORT=8000

# Tesseract OCR with English language data (add e.g. tesseract-ocr-hin for Hindi).
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install -r requirements.txt

COPY backend/app ./app
COPY --from=frontend /build/dist ./static

# Never run as root.
RUN useradd --create-home --uid 1000 sherlock
USER sherlock

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\", \"8000\")}/api/health', timeout=4)"

# --proxy-headers lets the rate limiter see real client IPs behind the host's proxy.
# --no-access-log: request URLs contain session IDs and download tokens, which
# must not end up in the hosting provider's log storage.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*' --no-access-log"]
