import { useState } from "react";
import type { Finding } from "../types";
import { OriginBadge, RiskBadge } from "./Feedback";
import { EyeIcon, EyeOffIcon, InfoIcon, SparklesIcon } from "./Icons";

type Filter = "all" | "rule" | "ai";

interface Props {
  findings: Finding[];
  selected: Set<string>;
  showPage: boolean;
  onToggle: (id: string) => void;
  onSetMany: (ids: string[], value: boolean) => void;
  onFocusFinding: (finding: Finding | null) => void;
}

function FindingItem({
  finding,
  checked,
  showPage,
  onToggle,
  onFocus,
}: {
  finding: Finding;
  checked: boolean;
  showPage: boolean;
  onToggle: () => void;
  onFocus: (active: boolean) => void;
}) {
  const [revealed, setRevealed] = useState(false);
  const inputId = `finding-${finding.id}`;
  const descId = `${inputId}-desc`;
  const ai = finding.origin === "ai";

  return (
    <li
      className={`rounded-xl border p-3.5 transition-colors ${
        checked ? "border-accent/45 bg-accent-wash" : ai ? "border-ai/25 bg-ai/[0.04]" : "border-line bg-white/[0.02]"
      } hover:border-line-strong`}
      onMouseEnter={() => onFocus(true)}
      onMouseLeave={() => onFocus(false)}
      onFocus={() => onFocus(true)}
      onBlur={() => onFocus(false)}
    >
      <div className="flex items-start gap-3">
        <input
          id={inputId}
          type="checkbox"
          className="mt-1 h-4 w-4 shrink-0 cursor-pointer rounded accent-[#14B8A6] disabled:cursor-not-allowed"
          checked={checked}
          disabled={!finding.locatable}
          onChange={onToggle}
          aria-describedby={descId}
        />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5">
            <label htmlFor={inputId} className="cursor-pointer text-sm font-semibold">
              {finding.label}
            </label>
            <RiskBadge risk={finding.risk} />
            <OriginBadge origin={finding.origin} />
          </div>
          <div className="mt-2 flex items-center gap-2">
            <code className="min-w-0 break-all rounded-md border border-line bg-surface-sunken px-2 py-1 font-mono text-[13px] text-fg">
              {revealed ? finding.value : finding.masked}
            </code>
            <button
              type="button"
              className="shrink-0 rounded-md p-1.5 text-fg-muted hover:bg-white/[0.06] hover:text-fg"
              onClick={() => setRevealed((r) => !r)}
              aria-pressed={revealed}
              aria-label={revealed ? `Hide ${finding.label}` : `Reveal ${finding.label}`}
              title={revealed ? "Hide" : "Reveal on this screen only"}
            >
              {revealed ? <EyeOffIcon className="h-4 w-4" /> : <EyeIcon className="h-4 w-4" />}
            </button>
          </div>
          <p id={descId} className="mt-2 text-xs leading-relaxed text-fg-muted">
            {showPage && <span className="font-medium text-fg">Page {finding.page} · </span>}
            {finding.detail && finding.detail !== "AI suggestion" && <span>{finding.detail}. </span>}
            {finding.source === "ocr" && <span>Read with OCR. </span>}
            {finding.explanation}
          </p>
          {finding.ai_reason && (
            <p className="mt-1.5 flex items-start gap-1.5 text-xs leading-relaxed text-ai-bright/90">
              <SparklesIcon className="mt-px h-3.5 w-3.5 shrink-0" />
              <span>
                AI: {finding.ai_reason}
                {finding.confidence !== null && <> · {Math.round(finding.confidence * 100)}% confidence</>}
                {ai && " · suggestion, please verify"}
              </span>
            </p>
          )}
          {!finding.locatable && (
            <p className="mt-2 flex items-start gap-1.5 text-xs text-warn-fg">
              <InfoIcon className="mt-px h-3.5 w-3.5 shrink-0" />
              Its location on the page could not be determined, so it can't be redacted automatically. Remove it manually.
            </p>
          )}
        </div>
      </div>
    </li>
  );
}

export function FindingsList({ findings, selected, showPage, onToggle, onSetMany, onFocusFinding }: Props) {
  const [filter, setFilter] = useState<Filter>("all");
  const visible = findings.filter((f) =>
    filter === "all" ? true : filter === "ai" ? f.origin !== "rule" : f.origin !== "ai",
  );
  const selectableVisible = visible.filter((f) => f.locatable).map((f) => f.id);
  const aiOnly = findings.filter((f) => f.origin === "ai" && f.locatable);
  const counts = {
    all: findings.length,
    rule: findings.filter((f) => f.origin !== "ai").length,
    ai: findings.filter((f) => f.origin !== "rule").length,
  };

  return (
    <section aria-labelledby="findings-heading" className="panel flex flex-col">
      <div className="space-y-3 border-b border-line px-4 py-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 id="findings-heading" className="text-sm font-semibold">
            Findings <span className="font-normal text-fg-muted">({findings.length})</span>
          </h2>
          <div className="flex flex-wrap gap-1">
            <button
              type="button"
              className="btn-ghost px-2.5 py-1.5 text-xs"
              onClick={() => onSetMany(selectableVisible, true)}
              disabled={selectableVisible.every((id) => selected.has(id))}
            >
              Select all
            </button>
            <button
              type="button"
              className="btn-ghost px-2.5 py-1.5 text-xs"
              onClick={() => onSetMany(visible.map((f) => f.id), false)}
              disabled={!visible.some((f) => selected.has(f.id))}
            >
              Deselect all
            </button>
            {aiOnly.length > 0 && (
              <button
                type="button"
                className="btn-ghost px-2.5 py-1.5 text-xs text-ai-bright"
                onClick={() => onSetMany(aiOnly.map((f) => f.id), true)}
                disabled={aiOnly.every((f) => selected.has(f.id))}
              >
                <SparklesIcon className="h-3.5 w-3.5" /> Select AI suggestions
              </button>
            )}
          </div>
        </div>
        <div role="tablist" aria-label="Filter findings" className="inline-flex rounded-lg border border-line bg-surface-sunken p-0.5">
          {(["all", "rule", "ai"] as Filter[]).map((key) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={filter === key}
              onClick={() => setFilter(key)}
              className={`rounded-md px-3 py-1 text-xs font-medium transition-colors ${
                filter === key ? "bg-white/[0.09] text-fg" : "text-fg-muted hover:text-fg"
              }`}
            >
              {key === "all" ? "All" : key === "rule" ? "Rules" : "AI"} <span className="tabular-nums opacity-70">{counts[key]}</span>
            </button>
          ))}
        </div>
      </div>
      {visible.length === 0 ? (
        <p className="px-4 py-8 text-center text-sm text-fg-muted">No findings in this view.</p>
      ) : (
        <ul className="space-y-2.5 p-3" aria-label="Detected sensitive information">
          {visible.map((f) => (
            <FindingItem
              key={f.id}
              finding={f}
              checked={selected.has(f.id)}
              showPage={showPage}
              onToggle={() => onToggle(f.id)}
              onFocus={(active) => onFocusFinding(active ? f : null)}
            />
          ))}
        </ul>
      )}
    </section>
  );
}
