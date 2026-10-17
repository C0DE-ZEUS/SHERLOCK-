import { describe, expect, it } from "vitest";
import { toOcrWords } from "../services/ocr";
import { OCR_IDLE, buildStages } from "../services/stages";
import { validateFile } from "../services/validation";
import type { Health, ScanResult } from "../types";

const health = {
  status: "ok",
  ai: { enabled: true, available: true, provider: "ollama", model: "qwen3:4b", endpoint_host: "localhost", is_local: true, message: "" },
  deployment: "local",
  session_ttl_minutes: 30,
  ocr_available: false,
  ocr_message: "",
  max_upload_mb: 10,
  max_pdf_pages: 30,
  accepted_extensions: [],
} satisfies Health;

const scan = (sources: Array<"text" | "ocr" | "pending">, ai: ScanResult["ai"] = null): ScanResult => ({
  session_id: "s",
  kind: "pdf",
  file_name: "a.pdf",
  pages: sources.map((source, i) => ({ page: i + 1, width: 595, height: 842, source })),
  findings: [],
  warnings: [],
  ai,
});

describe("buildStages", () => {
  it("describes the upload in progress", () => {
    const stages = buildStages({ scan: null, ocr: OCR_IDLE, health, aiWanted: true, aiError: null });
    expect(stages.map((s) => s.state)).toEqual(["active", "pending", "pending", "pending"]);
  });

  it("skips OCR for text PDFs and waits for AI", () => {
    const [extract, ocr, rules, ai] = buildStages({ scan: scan(["text", "text"]), ocr: OCR_IDLE, health, aiWanted: true, aiError: null });
    expect(extract.detail).toMatch(/2 pages; 2 with a text layer/);
    expect(ocr.state).toBe("skipped");
    expect(rules.state).toBe("done");
    expect(ai.state).toBe("pending");
  });

  it("reports browser OCR progress and makes rules wait", () => {
    const stages = buildStages({
      scan: scan(["text", "pending", "pending"]),
      ocr: { state: "running", page: 2, total: 2, progress: 0.5 },
      health,
      aiWanted: true,
      aiError: null,
    });
    expect(stages[1]).toMatchObject({ state: "active", detail: "Reading page 2 of 2 in your browser…", progress: 0.75 });
    expect(stages[2].state).toBe("pending");
    expect(stages[3].detail).toMatch(/after OCR/);
  });

  it("reflects every AI job state truthfully", () => {
    const job = { chunks_total: 3, chunks_done: 1, added: 0, confirmed: 0, rejected: 0, truncated: false, message: "msg", elapsed_seconds: 75 };
    const ai = (state: "queued" | "running" | "done" | "failed" | "unavailable") =>
      buildStages({ scan: scan(["text"], { ...job, state }), ocr: OCR_IDLE, health, aiWanted: true, aiError: null })[3];
    expect(ai("running")).toMatchObject({ state: "active", progress: 1 / 3 });
    expect(ai("running").detail).toMatch(/part 2 of 3/);
    expect(ai("done")).toMatchObject({ state: "done", detail: "msg (1m 15s)" });
    expect(ai("running").detail).toMatch(/1m 15s elapsed/);
    expect(ai("failed").state).toBe("failed");
    expect(ai("unavailable").state).toBe("off");
    const off = buildStages({ scan: scan(["text"]), ocr: OCR_IDLE, health: { ...health, ai: { ...health.ai, enabled: false } }, aiWanted: true, aiError: null });
    expect(off[3]).toMatchObject({ state: "off" });
  });
});

describe("toOcrWords", () => {
  it("flattens Tesseract lines into words with line numbers", () => {
    const words = toOcrWords([
      { words: [{ text: "Hello", bbox: { x0: 1, y0: 2, x1: 3, y1: 4 } }, { text: "  ", bbox: { x0: 0, y0: 0, x1: 0, y1: 0 } }] },
      { words: [{ text: "world", bbox: { x0: 5, y0: 6, x1: 7, y1: 8 } }] },
    ]);
    expect(words).toEqual([
      { text: "Hello", x0: 1, y0: 2, x1: 3, y1: 4, line: 0 },
      { text: "world", x0: 5, y0: 6, x1: 7, y1: 8, line: 1 },
    ]);
  });
});

describe("validateFile", () => {
  const file = (name: string, size: number) => new File([new Uint8Array(size)], name);
  it("accepts supported files and rejects others", () => {
    expect(validateFile(file("a.PDF", 10), 10)).toBeNull();
    expect(validateFile(file("a.jpeg", 10), 10)).toBeNull();
    expect(validateFile(file("a.gif", 10), 10)).toMatch(/unsupported/i);
    expect(validateFile(file("a.png", 0), 10)).toMatch(/empty/i);
    expect(validateFile(file("a.png", 2 * 1024 * 1024), 1)).toMatch(/1 MB/);
  });
});
