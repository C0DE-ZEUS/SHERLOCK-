import type { ReactNode } from "react";
import type { Origin, Risk } from "../types";
import { AlertIcon, InfoIcon, RulesIcon, SparklesIcon } from "./Icons";

export function ErrorBanner({ title, message, action }: { title?: string; message: string; action?: ReactNode }) {
  return (
    <div role="alert" className="flex gap-3 rounded-xl border border-danger/40 bg-danger-wash p-4 text-sm animate-fade-up">
      <AlertIcon className="mt-0.5 shrink-0 text-danger-fg" />
      <div className="min-w-0 flex-1">
        <p className="font-semibold text-danger-fg">{title ?? "Something went wrong"}</p>
        <p className="mt-1 text-fg/90">{message}</p>
        {action && <div className="mt-3">{action}</div>}
      </div>
    </div>
  );
}

export function Notice({ children, tone = "warn" }: { children: ReactNode; tone?: "warn" | "info" }) {
  const styles = tone === "warn" ? "border-warn/40 bg-warn-wash text-warn-fg" : "border-line bg-white/[0.03] text-fg-muted";
  const Icon = tone === "warn" ? AlertIcon : InfoIcon;
  return (
    <div role="status" className={`flex gap-3 rounded-xl border p-3.5 text-sm ${styles}`}>
      <Icon className="mt-0.5 h-[18px] w-[18px] shrink-0" />
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}

export function Spinner({ className = "" }: { className?: string }) {
  return (
    <svg className={`animate-spin ${className}`} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity="0.2" strokeWidth="3" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

export function ProgressBar({ value, tone = "accent", label }: { value: number | null; tone?: "accent" | "ai"; label: string }) {
  const color = tone === "ai" ? "bg-ai" : "bg-accent";
  return (
    <div
      className="relative h-1.5 w-full overflow-hidden rounded-full bg-white/[0.07]"
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={value === null ? undefined : Math.round(value * 100)}
    >
      {value === null ? (
        <div className={`absolute inset-y-0 w-1/3 rounded-full ${color} animate-shimmer`} />
      ) : (
        <div className={`h-full rounded-full ${color} transition-[width] duration-500`} style={{ width: `${Math.max(4, value * 100)}%` }} />
      )}
    </div>
  );
}

const RISK_STYLE: Record<Risk, { label: string; className: string; dots: number }> = {
  high: { label: "High", className: "border-danger/45 bg-danger-wash text-danger-fg", dots: 3 },
  medium: { label: "Medium", className: "border-warn/45 bg-warn-wash text-warn-fg", dots: 2 },
  low: { label: "Low", className: "border-line-strong bg-white/[0.04] text-fg-muted", dots: 1 },
};

/** Severity uses text plus a dot count, never colour alone. */
export function RiskBadge({ risk }: { risk: Risk }) {
  const style = RISK_STYLE[risk];
  return (
    <span className={`chip ${style.className}`}>
      <span className="flex gap-0.5" aria-hidden="true">
        {[0, 1, 2].map((i) => (
          <span key={i} className={`h-1.5 w-1.5 rounded-full bg-current ${i < style.dots ? "" : "opacity-25"}`} />
        ))}
      </span>
      {style.label} risk
    </span>
  );
}

/** Where a finding came from: deterministic rules, the AI model, or both. */
export function OriginBadge({ origin }: { origin: Origin }) {
  if (origin === "rule") {
    return (
      <span className="chip border-line-strong bg-white/[0.04] text-fg-muted">
        <RulesIcon className="h-3.5 w-3.5" /> Rule
      </span>
    );
  }
  if (origin === "ai") {
    return (
      <span className="chip border-ai/40 bg-ai-wash text-ai-bright">
        <SparklesIcon className="h-3.5 w-3.5" /> AI suggestion
      </span>
    );
  }
  return (
    <span className="chip border-ai/40 bg-ai-wash text-ai-bright">
      <RulesIcon className="h-3.5 w-3.5" /> Rule + AI
    </span>
  );
}

export function StatusDot({ tone }: { tone: "ok" | "warn" | "off" | "busy" }) {
  const color = { ok: "bg-accent", warn: "bg-warn", off: "bg-fg-subtle", busy: "bg-ai animate-pulse" }[tone];
  return <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${color}`} aria-hidden="true" />;
}
