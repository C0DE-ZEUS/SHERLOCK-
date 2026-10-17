import { forwardRef } from "react";
import { Dropzone, type DropzoneHandle } from "../components/Dropzone";
import { ErrorBanner, Notice } from "../components/Feedback";
import {
  CheckIcon,
  ClockIcon,
  EyeIcon,
  LockIcon,
  RulesIcon,
  ScanTextIcon,
  ServerIcon,
  ShieldIcon,
  SparklesIcon,
  UploadIcon,
} from "../components/Icons";
import { Toggle } from "../components/Toggle";
import type { Health } from "../types";

interface Props {
  health: Health | null;
  healthError: string | null;
  error: string | null;
  aiWanted: boolean;
  onAiWanted: (value: boolean) => void;
  onFile: (file: File) => void;
}

const RULES = [
  "Email addresses and phone numbers (Indian and international)",
  "Links carrying tokens, keys or session codes",
  "Aadhaar- and PAN-format IDs (checksum validated)",
  "Bank account numbers, IFSC codes and payment cards",
  "API keys, private keys, JWTs and labelled passwords",
];

const AI_FINDS = [
  "Names, dates of birth and other personal identifiers",
  "Home and postal addresses",
  "Passwords written in plain sentences",
  "Salaries, prices and private financial details",
  "Confidential business information",
];

export function aiToggleText(health: Health | null): { disabled: boolean; description: string } {
  if (!health) return { disabled: true, description: "Checking whether an AI model is available…" };
  const ai = health.ai;
  if (!ai.enabled) return { disabled: true, description: "AI detection is turned off on this server. Rule-based detection still runs." };
  if (!ai.available) return { disabled: true, description: `${ai.message} Rule-based detection still runs.` };
  if (ai.is_local) {
    return {
      disabled: false,
      description: `${ai.model} runs on this computer through ${ai.provider === "ollama" ? "Ollama" : ai.endpoint_host}. Text never leaves the machine. On a laptop CPU expect about a minute per page.`,
    };
  }
  return {
    disabled: false,
    description: `Extracted text is sent to ${ai.endpoint_host} (${ai.model}) for analysis. Leave this off if that is not acceptable.`,
  };
}

export const UploadPage = forwardRef<DropzoneHandle, Props>(function UploadPage(
  { health, healthError, error, aiWanted, onAiWanted, onFile },
  dropzoneRef,
) {
  const hosted = health?.deployment === "hosted";
  const ttl = health?.session_ttl_minutes ?? 30;
  const toggle = aiToggleText(health);

  return (
    <>
      {/* Hero */}
      <section className="relative overflow-hidden">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 bg-[linear-gradient(rgba(255,255,255,0.025)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.025)_1px,transparent_1px)] bg-[size:48px_48px] [mask-image:radial-gradient(ellipse_at_top,black_30%,transparent_75%)]"
        />
        <div className="relative mx-auto grid max-w-7xl items-start gap-10 px-4 pb-16 pt-12 sm:px-6 lg:grid-cols-[1.05fr_1fr] lg:gap-14 lg:pb-24 lg:pt-20">
          <div className="animate-fade-up">
            <span className="chip border-accent/30 bg-accent-wash text-accent-bright">
              <ShieldIcon className="h-3.5 w-3.5" /> Privacy-first document redaction
            </span>
            <h1 className="mt-5 text-4xl font-semibold leading-[1.08] tracking-tight sm:text-5xl lg:text-[3.4rem]">
              Find the hidden.
              <br />
              <span className="text-accent-bright">Protect the personal.</span>
            </h1>
            <p className="mt-5 max-w-xl text-base leading-relaxed text-fg-muted sm:text-lg">
              Sherlock scans screenshots, images and PDFs for personal data and secrets, lets you review
              every finding, and produces a copy where the selected content is permanently removed, not
              just covered.
            </p>
            <ul className="mt-7 grid max-w-xl gap-3 sm:grid-cols-2">
              {[
                [RulesIcon, "Precise rule-based detection"],
                [SparklesIcon, "Optional AI for context-aware finds"],
                [ScanTextIcon, "OCR for screenshots and scans"],
                [LockIcon, "Real redaction, verified before download"],
              ].map(([Icon, text]) => {
                const I = Icon as typeof RulesIcon;
                return (
                  <li key={text as string} className="flex items-center gap-2.5 text-sm text-fg/90">
                    <span className="flex h-7 w-7 items-center justify-center rounded-lg border border-line bg-white/[0.04]">
                      <I className="h-4 w-4 text-accent-bright" />
                    </span>
                    {text as string}
                  </li>
                );
              })}
            </ul>
            <p className="mt-7 max-w-xl text-sm text-fg-subtle">
              {hosted
                ? `Files are processed on the Sherlock server, never stored permanently, and deleted when you start over or after ${ttl} minutes.`
                : "Files are processed by the Sherlock backend on your own computer and deleted when you start over."}{" "}
              No account needed.
            </p>
          </div>

          <div id="upload" className="glass scroll-mt-24 p-5 sm:p-6 animate-fade-up [animation-delay:80ms]">
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-base font-semibold">Scan a document</h2>
              <span className="chip border-line bg-white/[0.03] text-fg-muted">
                <LockIcon className="h-3.5 w-3.5" /> No account
              </span>
            </div>
            <div className="mt-4 space-y-3">
              {healthError && <ErrorBanner title="Backend not reachable" message={healthError} />}
              {error && <ErrorBanner title="That file couldn't be scanned" message={error} />}
              <Dropzone
                ref={dropzoneRef}
                maxMb={health?.max_upload_mb ?? 10}
                maxPages={health?.max_pdf_pages ?? 30}
                onFile={onFile}
              />
              <div className="rounded-xl border border-line bg-white/[0.02] p-4">
                <Toggle
                  id="ai-toggle"
                  label="Contextual AI detection"
                  description={toggle.description}
                  checked={aiWanted && !toggle.disabled}
                  disabled={toggle.disabled}
                  onChange={onAiWanted}
                />
              </div>
              {health && !health.ocr_available && (
                <Notice tone="info">
                  Images and scanned pages are read with OCR inside your browser. The first time, this loads
                  about 10 MB of OCR data from this site.
                </Notice>
              )}
            </div>
          </div>
        </div>
      </section>

      {/* How it works */}
      <section id="how" className="scroll-mt-20 border-t border-line">
        <div className="mx-auto max-w-7xl px-4 py-16 sm:px-6">
          <p className="eyebrow">How it works</p>
          <h2 className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">Four steps, and you approve every one</h2>
          <ol className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {[
              [UploadIcon, "Upload", "Drop a PNG, JPG or PDF. Nothing is uploaded anywhere except the Sherlock backend."],
              [ScanTextIcon, "Detect", "Text is extracted (with OCR when needed), checked by precise rules and, optionally, a local AI model."],
              [EyeIcon, "Review", "Every finding shows its type, risk and source. Values stay masked until you choose to reveal one."],
              [ShieldIcon, "Redact & download", "Selected content is removed from a new copy, which is re-checked before you can download it."],
            ].map(([Icon, title, body], i) => {
              const I = Icon as typeof UploadIcon;
              return (
                <li key={title as string} className="panel p-5">
                  <div className="flex items-center justify-between">
                    <span className="flex h-9 w-9 items-center justify-center rounded-lg border border-accent/30 bg-accent-wash">
                      <I className="h-[18px] w-[18px] text-accent-bright" />
                    </span>
                    <span className="font-mono text-xs text-fg-subtle">0{i + 1}</span>
                  </div>
                  <h3 className="mt-4 font-semibold">{title as string}</h3>
                  <p className="mt-1.5 text-sm leading-relaxed text-fg-muted">{body as string}</p>
                </li>
              );
            })}
          </ol>
        </div>
      </section>

      {/* What it finds */}
      <section id="detects" className="scroll-mt-20 border-t border-line">
        <div className="mx-auto max-w-7xl px-4 py-16 sm:px-6">
          <p className="eyebrow">What it finds</p>
          <h2 className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">Two detection layers that check each other</h2>
          <div className="mt-8 grid gap-4 lg:grid-cols-2">
            <div className="panel p-6">
              <h3 className="flex items-center gap-2 font-semibold">
                <RulesIcon className="h-5 w-5 text-accent-bright" /> Rule-based detection
              </h3>
              <p className="mt-1 text-sm text-fg-muted">Deterministic patterns with checksums and context checks. Always on.</p>
              <ul className="mt-4 space-y-2.5">
                {RULES.map((r) => (
                  <li key={r} className="flex gap-2.5 text-sm text-fg/90">
                    <CheckIcon className="mt-0.5 h-4 w-4 shrink-0 text-accent" /> {r}
                  </li>
                ))}
              </ul>
            </div>
            <div className="panel border-ai/20 p-6">
              <h3 className="flex items-center gap-2 font-semibold">
                <SparklesIcon className="h-5 w-5 text-ai-bright" /> Contextual AI detection
              </h3>
              <p className="mt-1 text-sm text-fg-muted">
                A language model reads the text for things patterns miss. Its suggestions are matched back to the
                exact text on the page and are never redacted without your approval.
              </p>
              <ul className="mt-4 space-y-2.5">
                {AI_FINDS.map((r) => (
                  <li key={r} className="flex gap-2.5 text-sm text-fg/90">
                    <SparklesIcon className="mt-0.5 h-4 w-4 shrink-0 text-ai" /> {r}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </section>

      {/* Privacy */}
      <section id="privacy" className="scroll-mt-20 border-t border-line">
        <div className="mx-auto max-w-7xl px-4 py-16 sm:px-6">
          <p className="eyebrow">Privacy</p>
          <h2 className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">Built so your documents stay yours</h2>
          <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {[
              [ServerIcon, hosted ? "Processed on our server only" : "Processed on your computer",
                hosted
                  ? "Files go only to the Sherlock server. AI text analysis is used only if this server has a model configured, and the toggle tells you where text is sent."
                  : "The backend runs on your machine. With local Ollama, AI analysis never leaves it either."],
              [ClockIcon, "Temporary by design", `No database and no permanent storage. Working copies are deleted on Start over, and expire after ${ttl} minutes.`],
              [ShieldIcon, "Real, verified redaction", "PDF text is deleted from the file, image pixels are overwritten, metadata is stripped, and the result is re-checked."],
              [EyeIcon, "You stay in control", "Values are masked by default, AI findings are suggestions, and nothing is redacted until you confirm."],
            ].map(([Icon, title, body]) => {
              const I = Icon as typeof ServerIcon;
              return (
                <div key={title as string} className="panel p-5">
                  <I className="h-5 w-5 text-accent-bright" />
                  <h3 className="mt-3 font-semibold">{title as string}</h3>
                  <p className="mt-1.5 text-sm leading-relaxed text-fg-muted">{body as string}</p>
                </div>
              );
            })}
          </div>
          <p className="mt-6 text-sm text-fg-subtle">
            Automated detection can miss information. Sherlock helps you review documents; it does not replace your own
            check before sharing.
          </p>
        </div>
      </section>
    </>
  );
});
