import type { Health, OCRPage, RedactResult, ScanResult } from "../types";

/**
 * Base URL of the backend. Empty means "same origin": in development Vite
 * proxies /api to the local backend, and in a single-URL deployment the
 * backend serves this app. Set VITE_API_BASE only when the API lives on a
 * different domain (see .env.example).
 */
const BASE = ((import.meta.env.VITE_API_BASE as string | undefined) ?? "").replace(/\/+$/, "");

const UNREACHABLE =
  "Sherlock can't reach its backend. If you are running it yourself, start the backend on port 8000 (see the README); otherwise try again in a minute.";

export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public status = 0,
  ) {
    super(message);
  }
}

async function send(path: string, init?: RequestInit): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, init);
  } catch {
    throw new ApiError("backend_unreachable", UNREACHABLE);
  }
  if (!response.ok) {
    let code = "http_error";
    let message = `The request failed (HTTP ${response.status}).`;
    try {
      const body = await response.json();
      if (body?.error?.message) {
        code = body.error.code ?? code;
        message = body.error.message;
      }
    } catch {
      // Non-JSON error, e.g. the dev proxy could not reach the backend.
      if ([500, 502, 503, 504].includes(response.status)) {
        code = "backend_unreachable";
        message = UNREACHABLE;
      }
    }
    throw new ApiError(code, message, response.status);
  }
  return response;
}

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await send(path, init);
  return (await response.json()) as T;
}

const sessionPath = (id: string) => `/api/session/${encodeURIComponent(id)}`;

export const api = {
  health: () => json<Health>("/api/health"),

  scan: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return json<ScanResult>("/api/scan", { method: "POST", body: form });
  },

  ocrImage: async (sessionId: string, page: number) =>
    (await send(`${sessionPath(sessionId)}/ocr-image/${page}`)).blob(),

  submitOcr: (sessionId: string, pages: OCRPage[]) =>
    json<ScanResult>(`${sessionPath(sessionId)}/ocr`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pages }),
    }),

  startAi: (sessionId: string) => json<ScanResult>(`${sessionPath(sessionId)}/ai`, { method: "POST" }),

  aiProgress: (sessionId: string) => json<ScanResult>(`${sessionPath(sessionId)}/ai`),

  redact: (sessionId: string, findingIds: string[]) =>
    json<RedactResult>("/api/redact", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, finding_ids: findingIds }),
    }),

  deleteSession: async (sessionId: string, keepalive = false) => {
    await send(sessionPath(sessionId), { method: "DELETE", keepalive });
  },

  previewUrl: (sessionId: string, page: number) => `${BASE}${sessionPath(sessionId)}/preview/${page}`,

  outputPreviewUrl: (token: string, page: number) =>
    `${BASE}/api/download/${encodeURIComponent(token)}/preview/${page}`,

  downloadUrl: (token: string) => `${BASE}/api/download/${encodeURIComponent(token)}`,
};
