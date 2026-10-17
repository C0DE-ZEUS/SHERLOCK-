// Copies the Tesseract.js worker, WebAssembly core and English language data
// into public/ocr so in-browser OCR is served by Sherlock itself (no CDN).
// Runs automatically before `npm run dev` and `npm run build`.
import { copyFileSync, existsSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const out = join(root, "public", "ocr");

const pkgDir = (name) => dirname(require.resolve(`${name}/package.json`));
const files = [
  [join(pkgDir("tesseract.js"), "dist", "worker.min.js"), join(out, "worker.min.js")],
  // LSTM-only cores (Sherlock uses the LSTM engine), with and without SIMD.
  [join(pkgDir("tesseract.js-core"), "tesseract-core-simd-lstm.wasm.js"), join(out, "core", "tesseract-core-simd-lstm.wasm.js")],
  [join(pkgDir("tesseract.js-core"), "tesseract-core-lstm.wasm.js"), join(out, "core", "tesseract-core-lstm.wasm.js")],
  // Compact English model (integer "best" LSTM, ~3 MB).
  [join(pkgDir("@tesseract.js-data/eng"), "4.0.0_best_int", "eng.traineddata.gz"), join(out, "lang", "eng.traineddata.gz")],
];

for (const [from, to] of files) {
  if (!existsSync(from)) {
    console.error(`[ocr-assets] missing ${from}. Run npm install.`);
    process.exit(1);
  }
  mkdirSync(dirname(to), { recursive: true });
  copyFileSync(from, to);
}
console.log(`[ocr-assets] copied ${files.length} files to public/ocr`);
