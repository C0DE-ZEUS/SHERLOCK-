import { useState } from "react";
import { DocumentPreview } from "../components/DocumentPreview";
import { Notice } from "../components/Feedback";
import { CheckIcon, DownloadIcon, FileIcon, RestartIcon, ShieldIcon } from "../components/Icons";
import { api } from "../services/api";
import type { RedactResult } from "../types";

interface Props {
  originalName: string;
  result: RedactResult;
  hosted: boolean;
  onBack: () => void;
  onReset: () => void;
}

const FORMAT: Record<string, string> = { "application/pdf": "PDF", "image/png": "PNG", "image/jpeg": "JPEG" };

export function DonePage({ originalName, result, hosted, onBack, onReset }: Props) {
  const [page, setPage] = useState(1);
  return (
    <div className="mx-auto grid max-w-7xl gap-6 px-4 py-8 sm:px-6 lg:grid-cols-[420px_minmax(0,1fr)]">
      <section className="space-y-4" aria-labelledby="done-heading">
        <div className="glass p-6 animate-fade-up">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl border border-accent/30 bg-accent-wash text-accent-bright">
            <CheckIcon />
          </div>
          <h1 id="done-heading" className="mt-4 text-2xl font-semibold tracking-tight">
            Redacted copy ready
          </h1>
          <p className="mt-2 text-sm text-fg-muted">
            {result.redacted_count} {result.redacted_count === 1 ? "item was" : "items were"} permanently removed in a new
            file. The output passed Sherlock's verification checks.
          </p>

          <div className="mt-5 space-y-2.5">
            <div className="flex items-center gap-3 rounded-xl border border-line bg-white/[0.02] p-3">
              <FileIcon className="h-5 w-5 shrink-0 text-fg-subtle" />
              <div className="min-w-0 flex-1">
                <p className="text-xs text-fg-muted">Original · not modified</p>
                <p className="truncate text-sm">{originalName}</p>
              </div>
            </div>
            <div className="flex items-center gap-3 rounded-xl border border-accent/35 bg-accent-wash p-3">
              <ShieldIcon className="h-5 w-5 shrink-0 text-accent-bright" />
              <div className="min-w-0 flex-1">
                <p className="text-xs text-accent-bright">
                  Redacted · {FORMAT[result.media_type] ?? "file"} · {result.page_count} {result.page_count === 1 ? "page" : "pages"}
                </p>
                <p className="truncate text-sm">{result.file_name}</p>
              </div>
            </div>
          </div>

          <a className="btn-primary mt-5 w-full" href={api.downloadUrl(result.download_token)} download={result.file_name}>
            <DownloadIcon className="h-4 w-4" /> Download redacted file
          </a>
          <div className="mt-3 grid grid-cols-2 gap-2">
            <button type="button" className="btn-secondary" onClick={onBack}>
              Change selection
            </button>
            <button type="button" className="btn-secondary" onClick={onReset}>
              <RestartIcon className="h-4 w-4" /> Start over
            </button>
          </div>
        </div>

        <Notice>
          <p className="font-semibold">Check the file before you share it</p>
          <p className="mt-0.5">
            Automated detection can miss information. Open the downloaded file and confirm nothing sensitive remains.
            Start over to delete the temporary copies {hosted ? "from the server" : "from this computer"}.
          </p>
        </Notice>

        <div className="panel p-5">
          <h2 className="text-sm font-semibold">What Sherlock verified</h2>
          <ul className="mt-3 space-y-2">
            {result.checks.map((c) => (
              <li key={c} className="flex gap-2 text-sm text-fg-muted">
                <CheckIcon className="mt-0.5 h-4 w-4 shrink-0 text-accent" />
                {c}
              </li>
            ))}
          </ul>
        </div>
      </section>

      <DocumentPreview
        label="Redacted output"
        pageCount={result.page_count}
        page={page}
        onPageChange={setPage}
        imageUrl={(p) => api.outputPreviewUrl(result.download_token, p)}
      />
    </div>
  );
}
