import { useEffect, useMemo, useRef, useState } from "react";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { DocumentPreview } from "../components/DocumentPreview";
import { ErrorBanner, Notice, Spinner } from "../components/Feedback";
import { FindingsList } from "../components/FindingsList";
import { CheckIcon, FileIcon, RestartIcon, ShieldIcon, SparklesIcon } from "../components/Icons";
import { ProcessingPanel, type Stage } from "../components/ProcessingPanel";
import { ResultsSummary } from "../components/ResultsSummary";
import { api } from "../services/api";
import type { Finding, ScanResult } from "../types";

interface Props {
  scan: ScanResult;
  stages: Stage[];
  /** Selection to restore when returning from the completion screen. */
  initialSelected?: string[];
  error: string | null;
  redacting: boolean;
  canRunAi: boolean;
  onRunAi: () => void;
  onRedact: (ids: string[]) => void;
  onReset: () => void;
}

const RISK_ORDER = { high: 0, medium: 1, low: 2 } as const;

export function ReviewPage({ scan, stages, initialSelected, error, redacting, canRunAi, onRunAi, onRedact, onReset }: Props) {
  const findings = useMemo(
    () =>
      [...scan.findings].sort(
        (a, b) => a.page - b.page || RISK_ORDER[a.risk] - RISK_ORDER[b.risk] || (a.origin === "ai" ? 1 : 0) - (b.origin === "ai" ? 1 : 0),
      ),
    [scan.findings],
  );
  const [selected, setSelected] = useState<Set<string>>(
    () => new Set(initialSelected ?? scan.findings.filter((f) => f.default_selected).map((f) => f.id)),
  );
  // Findings arrive later from OCR and AI; pre-select new ones only if the
  // backend recommends it (AI suggestions never are).
  const known = useRef(new Set(scan.findings.map((f) => f.id)));
  useEffect(() => {
    const fresh = scan.findings.filter((f) => !known.current.has(f.id));
    if (fresh.length === 0) return;
    fresh.forEach((f) => known.current.add(f.id));
    const preselect = fresh.filter((f) => f.default_selected).map((f) => f.id);
    if (preselect.length) setSelected((prev) => new Set([...prev, ...preselect]));
  }, [scan.findings]);

  const [page, setPage] = useState(findings[0]?.page ?? 1);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);

  const toggle = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const setMany = (ids: string[], value: boolean) =>
    setSelected((prev) => {
      const next = new Set(prev);
      ids.forEach((id) => (value ? next.add(id) : next.delete(id)));
      return next;
    });
  const focusFinding = (f: Finding | null) => {
    setActiveId(f?.id ?? null);
    if (f && f.page !== page) setPage(f.page);
  };

  const ocrPending = scan.pages.some((p) => p.source === "pending");
  const aiRunning = scan.ai?.state === "queued" || scan.ai?.state === "running";
  const chosen = findings.filter((f) => selected.has(f.id));
  const pageCount = scan.pages.length;
  // AI runs in the background; only extraction and OCR block the review.
  const working = stages.some((s) => s.state === "active" && s.key !== "ai");

  const byCategory = new Map<string, number>();
  chosen.forEach((f) => byCategory.set(f.label, (byCategory.get(f.label) ?? 0) + 1));

  return (
    <div className="mx-auto max-w-7xl px-4 pb-36 pt-8 sm:px-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="flex items-center gap-1.5 text-sm text-fg-muted">
            <FileIcon className="h-4 w-4 shrink-0" />
            <span className="truncate">{scan.file_name}</span>
            <span aria-hidden="true">·</span>
            <span>{pageCount === 1 ? "1 page" : `${pageCount} pages`}</span>
          </p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">
            {working
              ? "Scanning your document"
              : findings.length === 0
                ? "No sensitive information found"
                : `${findings.length} possible ${findings.length === 1 ? "finding" : "findings"}`}
          </h1>
          <p className="mt-1 text-sm text-fg-muted">
            {aiRunning
              ? "You can start reviewing now; AI suggestions will appear here when the analysis finishes."
              : "Review each item, choose what to remove, then redact. Nothing is changed until you confirm."}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {canRunAi && (
            <button type="button" className="btn-secondary" onClick={onRunAi}>
              <SparklesIcon className="h-4 w-4 text-ai-bright" /> {scan.ai?.state === "failed" ? "Retry AI analysis" : "Run AI analysis"}
            </button>
          )}
          <button type="button" className="btn-secondary" onClick={onReset} disabled={redacting}>
            <RestartIcon className="h-4 w-4" /> Start over
          </button>
        </div>
      </div>

      <div className="mt-6 space-y-4">
        <ProcessingPanel stages={stages} />
        {error && <ErrorBanner title="Something went wrong" message={error} />}
        {scan.warnings.map((w) => (
          <Notice key={w}>{w}</Notice>
        ))}
        {ocrPending && !working && (
          <Notice>Some pages have not been read yet, so they were not checked. Start over to try again.</Notice>
        )}
        <ResultsSummary findings={findings} selectedCount={chosen.length} />
      </div>

      {findings.length === 0 && !working ? (
        <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_380px]">
          <DocumentPreview label="Original" pageCount={pageCount} page={page} onPageChange={setPage} imageUrl={(p) => api.previewUrl(scan.session_id, p)} />
          <div className="panel h-fit p-6">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl border border-accent/30 bg-accent-wash text-accent-bright">
              <ShieldIcon />
            </div>
            <h2 className="mt-4 font-semibold">Nothing Sherlock recognises</h2>
            <p className="mt-2 text-sm text-fg-muted">
              No supported sensitive information was detected. Detection can still miss signatures, faces, handwriting,
              or unusual formats, so check the document yourself before sharing it.
            </p>
            <button type="button" className="btn-primary mt-5" onClick={onReset}>
              Scan another file
            </button>
          </div>
        </div>
      ) : (
        <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_440px]">
          <div className="lg:sticky lg:top-24 lg:self-start">
            <DocumentPreview
              label="Original"
              badge="planned redactions shown"
              pageCount={pageCount}
              page={page}
              onPageChange={setPage}
              imageUrl={(p) => api.previewUrl(scan.session_id, p)}
              findings={findings}
              selected={selected}
              activeId={activeId}
            />
          </div>
          {findings.length > 0 ? (
            <FindingsList
              findings={findings}
              selected={selected}
              showPage={scan.kind === "pdf"}
              onToggle={toggle}
              onSetMany={setMany}
              onFocusFinding={focusFinding}
            />
          ) : (
            <div className="panel flex h-48 items-center justify-center gap-3 text-sm text-fg-muted">
              <Spinner className="h-5 w-5" /> Looking for sensitive information…
            </div>
          )}
        </div>
      )}

      {findings.length > 0 && (
        <div className="fixed inset-x-0 bottom-0 z-20 border-t border-line bg-bg/85 backdrop-blur-xl">
          <div className="mx-auto flex max-w-7xl flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:px-6">
            <p className="text-sm" aria-live="polite">
              <span className="font-semibold">
                {chosen.length} of {findings.length} selected.
              </span>{" "}
              <span className="text-fg-muted">
                {ocrPending ? "Waiting for OCR to finish." : "Only selected findings will be redacted."}
              </span>
            </p>
            <button
              type="button"
              className="btn-primary sm:min-w-[200px]"
              disabled={chosen.length === 0 || redacting || ocrPending}
              onClick={() => setConfirming(true)}
            >
              {redacting ? (
                <>
                  <Spinner className="h-4 w-4" /> Redacting…
                </>
              ) : (
                <>
                  <CheckIcon className="h-4 w-4" /> Review & redact
                </>
              )}
            </button>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={confirming}
        title={`Redact ${chosen.length} ${chosen.length === 1 ? "item" : "items"}?`}
        confirmLabel="Redact permanently"
        onCancel={() => setConfirming(false)}
        onConfirm={() => {
          setConfirming(false);
          onRedact(chosen.map((f) => f.id));
        }}
      >
        <p>
          Sherlock will create a <span className="text-fg">new file</span> with the selected content permanently removed.
          Your original file is not changed.
        </p>
        <ul className="mt-3 space-y-1">
          {[...byCategory.entries()].map(([label, count]) => (
            <li key={label} className="flex justify-between gap-4 rounded-md bg-white/[0.03] px-3 py-1.5 text-fg/90">
              <span>{label}</span>
              <span className="tabular-nums text-fg-muted">{count}</span>
            </li>
          ))}
        </ul>
        {aiRunning && (
          <p className="mt-3 text-warn-fg">AI analysis is still running. Suggestions that arrive later will not be included.</p>
        )}
        <p className="mt-3">Unselected findings stay in the document.</p>
      </ConfirmDialog>
    </div>
  );
}
