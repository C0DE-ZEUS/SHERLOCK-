import type { Stage } from "../components/ProcessingPanel";
import type { Health, ScanResult } from "../types";

export interface OcrProgress {
  state: "idle" | "running" | "done" | "failed";
  page: number; // 1-based position in the queue of pages being read
  total: number;
  progress: number; // 0-1 within the current page
  error?: string;
}

export const OCR_IDLE: OcrProgress = { state: "idle", page: 0, total: 0, progress: 0 };

interface Input {
  scan: ScanResult | null;
  ocr: OcrProgress;
  health: Health | null;
  aiWanted: boolean;
  aiError: string | null;
}

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

export const formatElapsed = (s: number) => (s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`);

/** Describe each processing step honestly from real state (no timers). */
export function buildStages({ scan, ocr, health, aiWanted, aiError }: Input): Stage[] {
  const pending = scan ? scan.pages.filter((p) => p.source === "pending").length : 0;
  const ocrPages = scan ? scan.pages.filter((p) => p.source === "ocr").length : 0;
  const textPages = scan ? scan.pages.filter((p) => p.source === "text").length : 0;

  const extract: Stage = scan
    ? {
        key: "extract",
        label: "Text extraction",
        state: "done",
        detail:
          scan.kind === "image"
            ? "Image decoded and orientation corrected."
            : `${plural(scan.pages.length, "page")}; ${textPages} with a text layer.`,
      }
    : { key: "extract", label: "Text extraction", state: "active", detail: "Uploading and reading the file…", progress: null };

  let ocrStage: Stage;
  if (!scan) {
    ocrStage = { key: "ocr", label: "OCR", state: "pending", detail: "Runs only for images and scanned pages." };
  } else if (pending === 0 && ocrPages === 0) {
    ocrStage = { key: "ocr", label: "OCR", state: "skipped", detail: "Text layer found, so OCR was not needed." };
  } else if (pending === 0) {
    ocrStage = {
      key: "ocr",
      label: "OCR",
      state: "done",
      detail: ocr.state === "done" ? `Read ${plural(ocrPages, "page")} in your browser (Tesseract.js).` : `Read ${plural(ocrPages, "page")} on the server (Tesseract).`,
    };
  } else if (ocr.state === "failed") {
    ocrStage = { key: "ocr", label: "OCR", state: "failed", detail: ocr.error ?? "In-browser OCR failed." };
  } else if (ocr.state === "running") {
    const fraction = ocr.total ? (ocr.page - 1 + ocr.progress) / ocr.total : null;
    ocrStage = {
      key: "ocr",
      label: "OCR",
      state: "active",
      detail: ocr.page === 0 ? "Loading the OCR engine in your browser…" : `Reading page ${ocr.page} of ${ocr.total} in your browser…`,
      progress: ocr.page === 0 ? null : fraction,
    };
  } else {
    ocrStage = { key: "ocr", label: "OCR", state: "pending", detail: `${plural(pending, "page")} waiting to be read in your browser.` };
  }

  const ruleCount = scan ? scan.findings.filter((f) => f.origin !== "ai").length : 0;
  const rules: Stage = !scan
    ? { key: "rules", label: "Rule detection", state: "pending", detail: "Pattern checks with checksums and context." }
    : pending > 0
      ? { key: "rules", label: "Rule detection", state: "pending", detail: "Waiting for OCR before checking those pages." }
      : { key: "rules", label: "Rule detection", state: "done", detail: `${plural(ruleCount, "finding")} from deterministic rules.` };

  return [extract, ocrStage, rules, aiStage(scan, health, aiWanted, aiError, pending)];
}

function aiStage(scan: ScanResult | null, health: Health | null, aiWanted: boolean, aiError: string | null, pending: number): Stage {
  const base = { key: "ai" as const, label: "AI analysis" };
  if (aiError) return { ...base, state: "failed", detail: aiError };
  if (!health) return { ...base, state: "pending", detail: "Checking for an AI model…" };
  const ai = health.ai;
  const job = scan?.ai ?? null;

  if (job) {
    switch (job.state) {
      case "queued":
        return { ...base, state: "active", detail: `Waiting for ${ai.model || "the model"}…`, progress: null };
      case "running": {
        const total = job.chunks_total;
        return {
          ...base,
          state: "active",
          detail: total
            ? `Analysing part ${Math.min(job.chunks_done + 1, total)} of ${total} with ${ai.model} · ${formatElapsed(job.elapsed_seconds)} elapsed. On a laptop CPU each part can take a minute or more.`
            : `Preparing text for ${ai.model}…`,
          progress: total ? job.chunks_done / total : null,
        };
      }
      case "done":
        return { ...base, state: "done", detail: `${job.message} (${formatElapsed(job.elapsed_seconds)})` };
      case "failed":
        return { ...base, state: "failed", detail: job.message || "AI analysis failed. Rule-based findings are unaffected." };
      case "unavailable":
        return { ...base, state: "off", detail: job.message };
    }
  }
  if (!ai.enabled) return { ...base, state: "off", detail: "AI detection is turned off on this server." };
  if (!ai.available) return { ...base, state: "off", detail: ai.message };
  if (!aiWanted) return { ...base, state: "off", detail: "Turned off. You can still run it from here." };
  if (pending > 0) return { ...base, state: "pending", detail: "Starts after OCR finishes." };
  return { ...base, state: "pending", detail: `Starts automatically with ${ai.model}.` };
}
