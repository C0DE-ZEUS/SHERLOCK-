import type { Finding } from "../types";

interface Props {
  findings: Finding[];
  selectedCount: number;
}

function Stat({ label, value, tone }: { label: string; value: number; tone?: "danger" | "ai" | "accent" }) {
  const color = tone === "danger" ? "text-danger-fg" : tone === "ai" ? "text-ai-bright" : tone === "accent" ? "text-accent-bright" : "text-fg";
  return (
    <div className="rounded-xl border border-line bg-white/[0.02] px-4 py-3">
      <dt className="text-xs font-medium text-fg-muted">{label}</dt>
      <dd className={`mt-1 text-2xl font-semibold tabular-nums ${color}`}>{value}</dd>
    </div>
  );
}

export function ResultsSummary({ findings, selectedCount }: Props) {
  const high = findings.filter((f) => f.risk === "high").length;
  const rules = findings.filter((f) => f.origin !== "ai").length;
  const ai = findings.filter((f) => f.origin === "ai").length;

  const categories = new Map<string, number>();
  for (const f of findings) categories.set(f.label, (categories.get(f.label) ?? 0) + 1);
  const topCategories = [...categories.entries()].sort((a, b) => b[1] - a[1]).slice(0, 8);

  return (
    <section aria-labelledby="summary-heading" className="space-y-3">
      <h2 id="summary-heading" className="sr-only">
        Results summary
      </h2>
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <Stat label="Findings" value={findings.length} />
        <Stat label="High risk" value={high} tone="danger" />
        <Stat label="Rule-based" value={rules} />
        <Stat label="AI suggestions" value={ai} tone="ai" />
        <Stat label="Selected to redact" value={selectedCount} tone="accent" />
      </dl>
      {topCategories.length > 0 && (
        <ul className="flex flex-wrap gap-2" aria-label="Findings by category">
          {topCategories.map(([label, count]) => (
            <li key={label} className="chip border-line bg-white/[0.03] text-fg-muted">
              {label}
              <span className="rounded-full bg-white/[0.08] px-1.5 text-[11px] font-semibold tabular-nums text-fg">{count}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
