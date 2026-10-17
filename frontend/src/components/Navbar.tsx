import type { Health } from "../types";
import { StatusDot } from "./Feedback";
import { ScanTextIcon, SparklesIcon } from "./Icons";

/** Wordmark: a document with a magnifying glass, drawn inline. */
export function LogoMark({ size = 30 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" aria-hidden="true" focusable="false">
      <rect width="32" height="32" rx="8" fill="#14B8A6" fillOpacity="0.12" />
      <rect x="0.5" y="0.5" width="31" height="31" rx="7.5" stroke="#14B8A6" strokeOpacity="0.35" />
      <path d="M9 7h8l4 4v8" stroke="#E2E8F0" strokeWidth="1.7" strokeLinejoin="round" />
      <path d="M9 7v18h6" stroke="#E2E8F0" strokeWidth="1.7" strokeLinejoin="round" />
      <path d="M12 12.5h5M12 16h3" stroke="#94A3B8" strokeWidth="1.6" strokeLinecap="round" />
      <circle cx="20" cy="20" r="4.3" stroke="#2DD4BF" strokeWidth="2.1" />
      <path d="m23.2 23.2 3.4 3.4" stroke="#2DD4BF" strokeWidth="2.3" strokeLinecap="round" />
    </svg>
  );
}

export function aiChip(health: Health | null, aiWanted: boolean) {
  if (!health) return { tone: "off" as const, text: "Checking AI…", title: "" };
  const ai = health.ai;
  if (!ai.enabled) return { tone: "off" as const, text: "AI disabled", title: ai.message };
  if (!ai.available) return { tone: "warn" as const, text: "AI unavailable", title: ai.message };
  if (!aiWanted) return { tone: "off" as const, text: "AI off", title: "Contextual AI detection is turned off." };
  return { tone: "ok" as const, text: `AI · ${ai.model}`, title: ai.message };
}

interface Props {
  health: Health | null;
  aiWanted: boolean;
  showLinks: boolean;
  onPrimary: () => void;
  primaryLabel: string;
}

export function Navbar({ health, aiWanted, showLinks, onPrimary, primaryLabel }: Props) {
  const chip = aiChip(health, aiWanted);
  return (
    <header className="sticky top-0 z-30 border-b border-line bg-bg/75 backdrop-blur-xl">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-4 px-4 sm:px-6">
        <div className="flex items-center gap-8">
          <a href="/" className="flex items-center gap-2.5 rounded-md" aria-label="Sherlock home">
            <LogoMark />
            <span className="text-[17px] font-semibold tracking-tight">Sherlock</span>
          </a>
          {showLinks && (
            <nav aria-label="Main" className="hidden items-center gap-1 md:flex">
              <a href="#how" className="btn-ghost py-1.5">
                How it works
              </a>
              <a href="#detects" className="btn-ghost py-1.5">
                What it finds
              </a>
              <a href="#privacy" className="btn-ghost py-1.5">
                Privacy
              </a>
            </nav>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className="chip hidden border-line bg-white/[0.03] text-fg-muted lg:inline-flex" title={chip.title}>
            <StatusDot tone={chip.tone} />
            <SparklesIcon className="h-3.5 w-3.5" />
            {chip.text}
          </span>
          {health && (
            <span
              className="chip hidden border-line bg-white/[0.03] text-fg-muted sm:inline-flex"
              title={health.ocr_available ? "Tesseract OCR runs on the server" : "OCR runs in your browser with Tesseract.js"}
            >
              <StatusDot tone="ok" />
              <ScanTextIcon className="h-3.5 w-3.5" />
              {health.ocr_available ? "OCR · server" : "OCR · browser"}
            </span>
          )}
          <button type="button" className="btn-primary px-3.5 py-2" onClick={onPrimary}>
            {primaryLabel}
          </button>
        </div>
      </div>
    </header>
  );
}
