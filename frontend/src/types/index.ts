export type Risk = "high" | "medium" | "low";
export type Origin = "rule" | "ai" | "rule+ai";

export interface AIStatus {
  enabled: boolean;
  available: boolean;
  provider: string;
  model: string;
  endpoint_host: string;
  /** True when the model runs on the same machine as the backend. */
  is_local: boolean;
  message: string;
}

export interface Health {
  status: "ok";
  ai: AIStatus;
  /** "local": running on the user's machine. "hosted": deployed for others. */
  deployment: "local" | "hosted";
  session_ttl_minutes: number;
  /** Server-side Tesseract. When false, the browser performs OCR. */
  ocr_available: boolean;
  ocr_message: string;
  max_upload_mb: number;
  max_pdf_pages: number;
  accepted_extensions: string[];
}

/** Highlight box as fractions (0-1) of the page width and height. */
export interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface Finding {
  id: string;
  category: string;
  label: string;
  risk: Risk;
  detail: string;
  masked: string;
  value: string;
  explanation: string;
  page: number;
  source: "text" | "ocr";
  origin: Origin;
  confidence: number | null;
  ai_reason: string;
  locatable: boolean;
  boxes: Box[];
  default_selected: boolean;
}

export interface PageInfo {
  page: number;
  width: number;
  height: number;
  /** "pending": waiting for in-browser OCR. */
  source: "text" | "ocr" | "pending" | "none";
}

export type AIJobState = "queued" | "running" | "done" | "failed" | "unavailable";

export interface AIJob {
  state: AIJobState;
  chunks_total: number;
  chunks_done: number;
  added: number;
  confirmed: number;
  rejected: number;
  truncated: boolean;
  message: string;
  elapsed_seconds: number;
}

export interface ScanResult {
  session_id: string;
  kind: "pdf" | "image";
  file_name: string;
  pages: PageInfo[];
  findings: Finding[];
  warnings: string[];
  ai: AIJob | null;
}

export interface RedactResult {
  download_token: string;
  file_name: string;
  media_type: string;
  page_count: number;
  redacted_count: number;
  checks: string[];
}

export interface OCRWord {
  text: string;
  x0: number;
  y0: number;
  x1: number;
  y1: number;
  line: number;
}

export interface OCRPage {
  page: number;
  width: number;
  height: number;
  words: OCRWord[];
}
