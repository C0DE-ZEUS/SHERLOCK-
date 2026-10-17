/**
 * In-browser OCR with Tesseract.js, used when the backend has no Tesseract.
 *
 * The engine, its WebAssembly core and the English model are served from
 * this app's own /ocr folder (copied by scripts/copy-ocr-assets.mjs), so no
 * third-party CDN is contacted. The library is loaded lazily, only when a
 * page actually needs OCR.
 */
import type { OCRPage, OCRWord } from "../types";

type Progress = (fraction: number) => void;

interface TesseractWord {
  text: string;
  bbox: { x0: number; y0: number; x1: number; y1: number };
}
interface TesseractLine {
  words: TesseractWord[];
}
interface RecognizeResult {
  data: { lines?: TesseractLine[] };
}
interface OcrWorker {
  recognize(image: Blob): Promise<RecognizeResult>;
  terminate(): Promise<unknown>;
}

const assetBase = `${import.meta.env.BASE_URL.replace(/\/$/, "")}/ocr`;

let progressListener: Progress | null = null;
let workerPromise: Promise<OcrWorker> | null = null;

function getWorker(): Promise<OcrWorker> {
  if (!workerPromise) {
    workerPromise = (async () => {
      const { createWorker, OEM } = await import("tesseract.js");
      const worker = await createWorker("eng", OEM.LSTM_ONLY, {
        workerPath: `${assetBase}/worker.min.js`,
        corePath: `${assetBase}/core`,
        langPath: `${assetBase}/lang`,
        workerBlobURL: false, // load the worker from our origin (CSP friendly)
        gzip: true,
        logger: (m: { status: string; progress: number }) => {
          if (m.status === "recognizing text") progressListener?.(m.progress);
        },
      });
      return worker as unknown as OcrWorker;
    })().catch((err) => {
      workerPromise = null;
      throw err;
    });
  }
  return workerPromise;
}

async function imageSize(blob: Blob): Promise<{ width: number; height: number }> {
  const bitmap = await createImageBitmap(blob);
  const size = { width: bitmap.width, height: bitmap.height };
  bitmap.close();
  return size;
}

/** Convert Tesseract's nested result into flat words with line numbers. */
export function toOcrWords(lines: TesseractLine[]): OCRWord[] {
  const words: OCRWord[] = [];
  lines.forEach((line, lineIndex) => {
    for (const w of line.words) {
      const text = w.text.trim();
      if (!text) continue;
      words.push({ text: text.slice(0, 100), x0: w.bbox.x0, y0: w.bbox.y0, x1: w.bbox.x1, y1: w.bbox.y1, line: lineIndex });
    }
  });
  return words;
}

export async function recognizePage(page: number, image: Blob, onProgress?: Progress): Promise<OCRPage> {
  const worker = await getWorker();
  progressListener = onProgress ?? null;
  try {
    const [{ width, height }, result] = await Promise.all([imageSize(image), worker.recognize(image)]);
    return { page, width, height, words: toOcrWords(result.data.lines ?? []) };
  } finally {
    progressListener = null;
  }
}

/** Free the worker's memory (called when the user starts over). */
export async function releaseOcr(): Promise<void> {
  if (!workerPromise) return;
  const pending = workerPromise;
  workerPromise = null;
  try {
    await (await pending).terminate();
  } catch {
    // already gone
  }
}
