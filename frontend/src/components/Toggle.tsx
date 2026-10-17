interface Props {
  checked: boolean;
  onChange: (value: boolean) => void;
  label: string;
  description?: string;
  disabled?: boolean;
  id: string;
}

/** Accessible switch (a checkbox with role="switch"). */
export function Toggle({ checked, onChange, label, description, disabled = false, id }: Props) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="min-w-0">
        <label htmlFor={id} className={`text-sm font-medium ${disabled ? "text-fg-subtle" : "text-fg"}`}>
          {label}
        </label>
        {description && (
          <p id={`${id}-desc`} className="mt-0.5 text-xs leading-relaxed text-fg-muted">
            {description}
          </p>
        )}
      </div>
      <span className="relative mt-0.5 inline-flex shrink-0">
        <input
          id={id}
          type="checkbox"
          role="switch"
          className="peer absolute inset-0 h-full w-full cursor-pointer opacity-0 disabled:cursor-not-allowed"
          checked={checked}
          disabled={disabled}
          aria-describedby={description ? `${id}-desc` : undefined}
          onChange={(e) => onChange(e.target.checked)}
        />
        <span
          aria-hidden="true"
          className="pointer-events-none h-6 w-11 rounded-full border border-line-strong bg-white/[0.08] transition-colors peer-checked:border-ai/60 peer-checked:bg-ai/80 peer-focus-visible:ring-2 peer-focus-visible:ring-accent peer-focus-visible:ring-offset-2 peer-focus-visible:ring-offset-bg peer-disabled:opacity-40"
        />
        <span
          aria-hidden="true"
          className="pointer-events-none absolute left-1 top-1 h-4 w-4 rounded-full bg-white shadow transition-transform peer-checked:translate-x-5"
        />
      </span>
    </div>
  );
}
