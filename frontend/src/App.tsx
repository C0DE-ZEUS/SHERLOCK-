import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { DropzoneHandle } from "./components/Dropzone";
import { Footer } from "./components/Footer";
import { FileIcon } from "./components/Icons";
import { Navbar } from "./components/Navbar";
import { ProcessingPanel } from "./components/ProcessingPanel";
import { DonePage } from "./pages/DonePage";
import { ReviewPage } from "./pages/ReviewPage";
import { UploadPage } from "./pages/UploadPage";
import { ApiError, api } from "./services/api";
import { recognizePage, releaseOcr } from "./services/ocr";
import { OCR_IDLE, buildStages, type OcrProgress } from "./services/stages";
import { validateFile } from "./services/validation";
import type { Health, OCRPage, RedactResult, ScanResult } from "./types";

type View =
  | { name: "upload" }
  | { name: "scanning"; fileName: string }
  | { name: "review"; selected?: string[] }
  | { name: "redacting"; selected: string[] }
  | { name: "done"; selected: string[]; result: RedactResult };

const AI_PREF_KEY = "sherlock.ai-enabled";
const POLL_MS = 3000;

const message = (err: unknown) =>
  err instanceof ApiError ? err.message : "Something unexpected went wrong. Please try again.";
const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

function readAiPref(): boolean {
  try {
    return localStorage.getItem(AI_PREF_KEY) !== "off";
  } catch {
    return true;
  }
}

export default function App() {
  const [view, setView] = useState<View>({ name: "upload" });
  const [scan, setScan] = useState<ScanResult | null>(null);
  const [ocr, setOcr] = useState<OcrProgress>(OCR_IDLE);
  const [aiError, setAiError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [aiWanted, setAiWantedState] = useState(readAiPref);

  const busy = useRef(false); // guards against duplicate submissions
  const activeSession = useRef<string | null>(null); // async work for old sessions is ignored
  const healthRef = useRef<Health | null>(null);
  const aiWantedRef = useRef(aiWanted);
  const dropzoneRef = useRef<DropzoneHandle>(null);
  healthRef.current = health;
  aiWantedRef.current = aiWanted;

  const hosted = health?.deployment === "hosted";
  const sessionId = scan?.session_id ?? null;

  useEffect(() => {
    api
      .health()
      .then((h) => {
        setHealth(h);
        setHealthError(null);
      })
      .catch((err) => setHealthError(message(err)));
  }, []);

  // Best effort: delete temporary files if the tab is closed mid-session.
  useEffect(() => {
    if (!sessionId) return;
    const onHide = () => {
      api.deleteSession(sessionId, true).catch(() => undefined);
    };
    window.addEventListener("pagehide", onHide);
    return () => window.removeEventListener("pagehide", onHide);
  }, [sessionId]);

  const setAiWanted = (value: boolean) => {
    setAiWantedState(value);
    try {
      localStorage.setItem(AI_PREF_KEY, value ? "on" : "off");
    } catch {
      // storage unavailable (private mode): the choice lasts for this visit
    }
  };

  const runAi = useCallback(async (sid: string) => {
    setAiError(null);
    try {
      let result = await api.startAi(sid);
      while (activeSession.current === sid) {
        setScan(result);
        const state = result.ai?.state;
        if (state !== "queued" && state !== "running") break;
        await sleep(POLL_MS);
        if (activeSession.current !== sid) return;
        result = await api.aiProgress(sid);
      }
    } catch (err) {
      if (activeSession.current === sid) setAiError(message(err));
    }
  }, []);

  /** After the upload: OCR pending pages in the browser, then start AI. */
  const continueScan = useCallback(
    async (initial: ScanResult) => {
      const sid = initial.session_id;
      const pending = initial.pages.filter((p) => p.source === "pending").map((p) => p.page);
      if (pending.length) {
        setOcr({ state: "running", page: 0, total: pending.length, progress: 0 });
        try {
          const pages: OCRPage[] = [];
          for (let i = 0; i < pending.length; i++) {
            const image = await api.ocrImage(sid, pending[i]);
            if (activeSession.current !== sid) return;
            setOcr({ state: "running", page: i + 1, total: pending.length, progress: 0 });
            pages.push(
              await recognizePage(pending[i], image, (progress) => {
                if (activeSession.current === sid) setOcr((o) => ({ ...o, progress }));
              }),
            );
          }
          if (activeSession.current !== sid) return;
          const updated = await api.submitOcr(sid, pages);
          if (activeSession.current !== sid) return;
          setScan(updated);
          setOcr({ state: "done", page: pending.length, total: pending.length, progress: 1 });
        } catch (err) {
          if (activeSession.current !== sid) return;
          const detail =
            err instanceof ApiError
              ? err.message
              : "In-browser OCR could not run. Try a recent version of Chrome, Edge or Firefox.";
          setOcr((o) => ({ ...o, state: "failed", error: detail }));
          return;
        }
      }
      if (aiWantedRef.current && healthRef.current?.ai.available) await runAi(sid);
    },
    [runAi],
  );

  const handleFile = useCallback(
    async (file: File) => {
      if (busy.current) return;
      const problem = validateFile(file, health?.max_upload_mb ?? 10);
      if (problem) {
        setError(problem);
        return;
      }
      busy.current = true;
      setError(null);
      setAiError(null);
      setOcr(OCR_IDLE);
      setScan(null);
      setView({ name: "scanning", fileName: file.name });
      window.scrollTo({ top: 0 });
      try {
        const result = await api.scan(file);
        activeSession.current = result.session_id;
        setScan(result);
        setView({ name: "review" });
        void continueScan(result);
      } catch (err) {
        setError(message(err));
        setView({ name: "upload" });
      } finally {
        busy.current = false;
      }
    },
    [health, continueScan],
  );

  const handleRedact = useCallback(
    async (ids: string[]) => {
      if (busy.current || !scan) return;
      busy.current = true;
      setError(null);
      setView({ name: "redacting", selected: ids });
      try {
        const result = await api.redact(scan.session_id, ids);
        setView({ name: "done", selected: ids, result });
        window.scrollTo({ top: 0 });
      } catch (err) {
        if (err instanceof ApiError && err.code === "session_not_found") {
          activeSession.current = null;
          setScan(null);
          setView({ name: "upload" });
        } else {
          setView({ name: "review", selected: ids });
        }
        setError(message(err));
      } finally {
        busy.current = false;
      }
    },
    [scan],
  );

  const handleReset = useCallback(() => {
    if (sessionId) api.deleteSession(sessionId).catch(() => undefined);
    activeSession.current = null;
    void releaseOcr();
    setScan(null);
    setOcr(OCR_IDLE);
    setAiError(null);
    setError(null);
    setView({ name: "upload" });
    window.scrollTo({ top: 0 });
  }, [sessionId]);

  const stages = useMemo(
    () => buildStages({ scan, ocr, health, aiWanted, aiError }),
    [scan, ocr, health, aiWanted, aiError],
  );

  const ocrPending = scan?.pages.some((p) => p.source === "pending") ?? false;
  const aiState = scan?.ai?.state;
  const canRunAi =
    !!scan &&
    !!health?.ai.available &&
    !ocrPending &&
    aiState !== "queued" &&
    aiState !== "running" &&
    aiState !== "done";

  const onPrimary = () => {
    if (view.name === "upload") {
      document.getElementById("upload")?.scrollIntoView({ block: "center" });
      dropzoneRef.current?.focus();
    } else {
      handleReset();
    }
  };

  return (
    <div className="relative flex min-h-screen flex-col overflow-x-hidden">
      {/* Restrained ambient light behind the page */}
      <div aria-hidden="true" className="pointer-events-none absolute inset-x-0 top-0 -z-0 h-[640px] overflow-hidden">
        <div className="absolute -left-40 -top-40 h-[480px] w-[480px] rounded-full bg-accent/[0.10] blur-[120px]" />
        <div className="absolute -right-32 -top-24 h-[420px] w-[420px] rounded-full bg-ai/[0.10] blur-[120px]" />
      </div>
      <a
        href="#main"
        className="sr-only z-50 rounded-md bg-surface px-3 py-2 text-sm focus:not-sr-only focus:absolute focus:left-3 focus:top-3"
      >
        Skip to content
      </a>
      <Navbar
        health={health}
        aiWanted={aiWanted}
        showLinks={view.name === "upload"}
        onPrimary={onPrimary}
        primaryLabel={view.name === "upload" ? "Scan a file" : "New scan"}
      />
      <main id="main" className="relative flex-1">
        {view.name === "upload" && (
          <UploadPage
            ref={dropzoneRef}
            health={health}
            healthError={healthError}
            error={error}
            aiWanted={aiWanted}
            onAiWanted={setAiWanted}
            onFile={handleFile}
          />
        )}
        {view.name === "scanning" && (
          <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6" aria-busy="true">
            <p className="flex items-center gap-1.5 text-sm text-fg-muted">
              <FileIcon className="h-4 w-4" />
              <span className="truncate">{view.fileName}</span>
            </p>
            <h1 className="mb-6 mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">Scanning your file</h1>
            <ProcessingPanel stages={stages} />
          </div>
        )}
        {scan && (view.name === "review" || view.name === "redacting") && (
          <ReviewPage
            key={scan.session_id}
            scan={scan}
            stages={stages}
            initialSelected={view.selected}
            error={error}
            redacting={view.name === "redacting"}
            canRunAi={canRunAi}
            onRunAi={() => void runAi(scan.session_id)}
            onRedact={handleRedact}
            onReset={handleReset}
          />
        )}
        {scan && view.name === "done" && (
          <DonePage
            originalName={scan.file_name}
            result={view.result}
            hosted={hosted}
            onBack={() => setView({ name: "review", selected: view.selected })}
            onReset={handleReset}
          />
        )}
      </main>
      <Footer hosted={hosted} />
    </div>
  );
}
