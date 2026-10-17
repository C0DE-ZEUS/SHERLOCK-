import type { ComponentType, SVGProps } from "react";
import { ProgressBar, Spinner } from "./Feedback";
import { AlertIcon, CheckIcon, FileIcon, RulesIcon, ScanTextIcon, SparklesIcon } from "./Icons";

export type StageState = "pending" | "active" | "done" | "skipped" | "failed" | "off";

export interface Stage {
  key: "extract" | "ocr" | "rules" | "ai";
  label: string;
  state: StageState;
  detail: string;
  /** 0-1 for determinate progress, null for indeterminate, undefined for none. */
  progress?: number | null;
}

const ICONS: Record<Stage["key"], ComponentType<SVGProps<SVGSVGElement>>> = {
  extract: FileIcon,
  ocr: ScanTextIcon,
  rules: RulesIcon,
  ai: SparklesIcon,
};

const STATE_TEXT: Record<StageState, string> = {
  pending: "Waiting",
  active: "In progress",
  done: "Done",
  skipped: "Not needed",
  failed: "Failed",
  off: "Off",
};

function StateIcon({ state, ai }: { state: StageState; ai: boolean }) {
  if (state === "active") return <Spinner className={`h-4 w-4 ${ai ? "text-ai" : "text-accent"}`} />;
  if (state === "done") return <CheckIcon className="h-4 w-4 text-accent" />;
  if (state === "failed") return <AlertIcon className="h-4 w-4 text-warn" />;
  return <span className="h-2 w-2 rounded-full bg-fg-subtle/60" aria-hidden="true" />;
}

export function ProcessingPanel({ stages, title = "Processing" }: { stages: Stage[]; title?: string }) {
  return (
    <section aria-labelledby="processing-heading" className="glass p-4 sm:p-5">
      <h2 id="processing-heading" className="sr-only">
        {title}
      </h2>
      <ol className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-live="polite">
        {stages.map((stage) => {
          const Icon = ICONS[stage.key];
          const ai = stage.key === "ai";
          const dim = stage.state === "pending" || stage.state === "off" || stage.state === "skipped";
          return (
            <li
              key={stage.key}
              className={`rounded-xl border p-3.5 transition-colors ${
                stage.state === "active"
                  ? ai
                    ? "border-ai/40 bg-ai-wash"
                    : "border-accent/40 bg-accent-wash"
                  : "border-line bg-white/[0.02]"
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className={`flex items-center gap-2 text-sm font-semibold ${dim ? "text-fg-muted" : "text-fg"}`}>
                  <Icon className={`h-4 w-4 ${ai ? "text-ai-bright" : "text-accent-bright"}`} />
                  {stage.label}
                </span>
                <span className="flex items-center gap-1.5 text-xs text-fg-muted">
                  <StateIcon state={stage.state} ai={ai} />
                  <span>{STATE_TEXT[stage.state]}</span>
                </span>
              </div>
              <p className="mt-2 min-h-[2.5em] text-xs leading-relaxed text-fg-muted">{stage.detail}</p>
              {stage.state === "active" && stage.progress !== undefined && (
                <div className="mt-2">
                  <ProgressBar value={stage.progress} tone={ai ? "ai" : "accent"} label={`${stage.label} progress`} />
                </div>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
