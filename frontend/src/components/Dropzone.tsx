import { forwardRef, useImperativeHandle, useRef, useState, type DragEvent } from "react";
import { ACCEPT_ATTR } from "../services/validation";
import { UploadIcon } from "./Icons";

interface Props {
  maxMb: number;
  maxPages: number;
  disabled?: boolean;
  onFile: (file: File) => void;
}

export interface DropzoneHandle {
  focus: () => void;
}

export const Dropzone = forwardRef<DropzoneHandle, Props>(function Dropzone(
  { maxMb, maxPages, disabled = false, onFile },
  ref,
) {
  const inputRef = useRef<HTMLInputElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const [dragging, setDragging] = useState(false);
  useImperativeHandle(ref, () => ({ focus: () => buttonRef.current?.focus() }));

  const pick = (files: FileList | null) => {
    if (!disabled && files && files.length > 0) onFile(files[0]);
  };

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragging(false);
    pick(event.dataTransfer.files);
  };

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      className={`group relative flex flex-col items-center justify-center rounded-xl border border-dashed px-6 py-10 text-center transition-colors ${
        dragging ? "border-accent bg-accent-wash" : "border-line-strong bg-white/[0.02] hover:border-accent/50"
      } ${disabled ? "opacity-60" : ""}`}
    >
      <div className="flex h-12 w-12 items-center justify-center rounded-xl border border-accent/30 bg-accent-wash text-accent-bright transition-transform group-hover:-translate-y-0.5">
        <UploadIcon width={24} height={24} />
      </div>
      <p className="mt-4 text-base font-semibold">Drop a file to scan</p>
      <p className="mt-1 text-sm text-fg-muted">Screenshots, photos or PDFs</p>
      <button ref={buttonRef} type="button" className="btn-primary mt-5" onClick={() => inputRef.current?.click()} disabled={disabled}>
        Browse files
      </button>
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT_ATTR}
        className="sr-only"
        aria-label="Upload a PDF, PNG, JPG or JPEG file"
        tabIndex={-1}
        disabled={disabled}
        onChange={(e) => {
          pick(e.target.files);
          e.target.value = "";
        }}
      />
      <p className="mt-5 text-xs text-fg-subtle">
        PDF, PNG, JPG · up to {maxMb} MB · PDFs up to {maxPages} pages
      </p>
    </div>
  );
});
