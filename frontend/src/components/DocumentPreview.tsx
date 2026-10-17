import { useEffect, useState } from "react";
import type { Finding } from "../types";
import { Spinner } from "./Feedback";
import { ChevronLeftIcon, ChevronRightIcon } from "./Icons";

interface Props {
  pageCount: number;
  page: number;
  onPageChange: (page: number) => void;
  imageUrl: (page: number) => string;
  /** Findings to highlight; omit for previews of the redacted output. */
  findings?: Finding[];
  selected?: Set<string>;
  activeId?: string | null;
  label: string;
  badge?: string;
}

export function DocumentPreview({
  pageCount,
  page,
  onPageChange,
  imageUrl,
  findings = [],
  selected,
  activeId,
  label,
  badge,
}: Props) {
  const [loaded, setLoaded] = useState(false);
  const [failed, setFailed] = useState(false);
  const src = imageUrl(page);

  useEffect(() => {
    setLoaded(false);
    setFailed(false);
  }, [src]);

  const onPage = findings.filter((f) => f.page === page && f.locatable);

  return (
    <div className="panel overflow-hidden">
      <div className="flex items-center justify-between gap-2 border-b border-line px-4 py-2.5">
        <h2 className="flex items-center gap-2 text-sm font-semibold">
          {label}
          {badge && <span className="chip border-line bg-white/[0.04] text-fg-muted">{badge}</span>}
        </h2>
        {pageCount > 1 && (
          <nav className="flex items-center gap-1" aria-label={`${label} pages`}>
            <button type="button" className="btn-ghost px-2 py-1.5" onClick={() => onPageChange(page - 1)} disabled={page <= 1} aria-label="Previous page">
              <ChevronLeftIcon />
            </button>
            <span className="min-w-[84px] text-center text-sm tabular-nums text-fg-muted" aria-live="polite">
              Page {page} of {pageCount}
            </span>
            <button type="button" className="btn-ghost px-2 py-1.5" onClick={() => onPageChange(page + 1)} disabled={page >= pageCount} aria-label="Next page">
              <ChevronRightIcon />
            </button>
          </nav>
        )}
      </div>
      <div className="flex justify-center bg-surface-sunken p-3 sm:p-5">
        <div className="relative inline-block max-w-full">
          {!loaded && !failed && (
            <div className="flex h-72 w-56 items-center justify-center">
              <Spinner className="h-6 w-6 text-fg-muted" />
            </div>
          )}
          {failed && <p className="px-6 py-16 text-center text-sm text-fg-muted">The preview could not be loaded.</p>}
          <img
            key={src}
            src={src}
            alt={`${label}, page ${page}`}
            onLoad={() => setLoaded(true)}
            onError={() => setFailed(true)}
            className={`block max-h-[72vh] max-w-full rounded-md bg-white shadow-lift ${loaded ? "" : "hidden"}`}
          />
          {loaded &&
            onPage.flatMap((f) =>
              f.boxes.map((b, i) => {
                const isSelected = selected?.has(f.id);
                const isActive = activeId === f.id;
                const style = isSelected
                  ? "border border-accent bg-[#0B1020]"
                  : f.origin === "ai"
                    ? "border-2 border-dashed border-ai bg-ai/15"
                    : "border-2 border-dashed border-warn bg-warn/15";
                return (
                  <span
                    key={`${f.id}-${i}`}
                    aria-hidden="true"
                    className={`pointer-events-none absolute rounded-[2px] transition-all ${style} ${
                      isActive ? "ring-4 ring-accent/70 ring-offset-1 ring-offset-white" : ""
                    }`}
                    style={{
                      left: `calc(${b.x * 100}% - 2px)`,
                      top: `calc(${b.y * 100}% - 2px)`,
                      width: `calc(${b.w * 100}% + 4px)`,
                      height: `calc(${b.h * 100}% + 4px)`,
                    }}
                  />
                );
              }),
            )}
        </div>
      </div>
      {findings.length > 0 && (
        <div className="flex flex-wrap gap-x-4 gap-y-1.5 border-t border-line px-4 py-2.5 text-xs text-fg-muted">
          <span className="inline-flex items-center gap-1.5">
            <span className="h-3 w-4 rounded-[2px] border border-accent bg-[#0B1020]" aria-hidden="true" />
            Will be redacted (hidden)
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-3 w-4 rounded-[2px] border-2 border-dashed border-warn bg-warn/15" aria-hidden="true" />
            Rule finding, not selected
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-3 w-4 rounded-[2px] border-2 border-dashed border-ai bg-ai/15" aria-hidden="true" />
            AI suggestion, not selected
          </span>
        </div>
      )}
    </div>
  );
}
