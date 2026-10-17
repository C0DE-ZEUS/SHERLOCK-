import { GithubIcon } from "./Icons";
import { LogoMark } from "./Navbar";

const GITHUB_URL = (import.meta.env.VITE_GITHUB_URL as string | undefined)?.trim();

export function Footer({ hosted }: { hosted: boolean }) {
  return (
    <footer className="border-t border-line bg-surface-sunken/60">
      <div className="mx-auto grid max-w-7xl gap-8 px-4 py-10 sm:px-6 md:grid-cols-[1.4fr_1fr_1fr]">
        <div>
          <div className="flex items-center gap-2.5">
            <LogoMark size={26} />
            <span className="font-semibold">Sherlock</span>
          </div>
          <p className="mt-3 max-w-sm text-sm text-fg-muted">
            Find the hidden. Protect the personal. Sherlock finds sensitive information in images and
            PDFs and creates a permanently redacted copy.
          </p>
          {GITHUB_URL && (
            <a href={GITHUB_URL} className="btn-ghost -ml-3 mt-3" target="_blank" rel="noreferrer noopener">
              <GithubIcon className="h-4 w-4" /> Source on GitHub
            </a>
          )}
        </div>
        <div>
          <h2 className="text-sm font-semibold">Privacy principles</h2>
          <ul className="mt-3 space-y-2 text-sm text-fg-muted">
            <li>No account, no tracking, no analytics</li>
            <li>{hosted ? "Files deleted automatically after processing" : "Files processed on your own computer"}</li>
            <li>AI suggestions are reviewed by you, never applied automatically</li>
            <li>Detection can miss things: always check the output</li>
          </ul>
        </div>
        <div>
          <h2 className="text-sm font-semibold">Built with</h2>
          <ul className="mt-3 space-y-2 text-sm text-fg-muted">
            <li>React, TypeScript, Tailwind CSS</li>
            <li>FastAPI and PyMuPDF redaction</li>
            <li>Tesseract OCR (server or in-browser)</li>
            <li>Optional local AI via Ollama</li>
          </ul>
        </div>
      </div>
    </footer>
  );
}
