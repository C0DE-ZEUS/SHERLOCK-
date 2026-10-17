import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import type { Finding, Health, ScanResult } from "../types";

vi.mock("../services/ocr", () => ({
  recognizePage: vi.fn(async (page: number) => ({
    page,
    width: 400,
    height: 200,
    words: [
      { text: "Email:", x0: 20, y0: 40, x1: 80, y1: 60, line: 0 },
      { text: "jane.doe@example.com", x0: 90, y0: 40, x1: 300, y1: 60, line: 0 },
    ],
  })),
  releaseOcr: vi.fn(async () => undefined),
}));

const aiOff = { enabled: true, available: false, provider: "ollama", model: "qwen3:4b", endpoint_host: "localhost", is_local: true, message: "Ollama is not reachable. Start Ollama to enable AI detection." };
const aiOn = { ...aiOff, available: true, message: "qwen3:4b via Ollama" };

const healthWith = (over: Partial<Health> = {}): Health => ({
  status: "ok",
  ai: aiOff,
  deployment: "local",
  session_ttl_minutes: 30,
  ocr_available: true,
  ocr_message: "Tesseract 5",
  max_upload_mb: 10,
  max_pdf_pages: 30,
  accepted_extensions: [".jpeg", ".jpg", ".pdf", ".png"],
  ...over,
});

const finding = (over: Partial<Finding>): Finding => ({
  id: "f1",
  category: "email",
  label: "Email address",
  risk: "medium",
  detail: "",
  masked: "ja***@example.com",
  value: "jane.doe@example.com",
  explanation: "A personal or work email address.",
  page: 1,
  source: "text",
  origin: "rule",
  confidence: null,
  ai_reason: "",
  locatable: true,
  boxes: [{ x: 0.1, y: 0.1, w: 0.2, h: 0.02 }],
  default_selected: true,
  ...over,
});

const aiFinding = finding({
  id: "a1",
  category: "ai_personal_identifier",
  label: "Personal identifier",
  risk: "high",
  masked: "A*** E******",
  value: "Asha Example",
  origin: "ai",
  confidence: 0.9,
  ai_reason: "Customer name",
  default_selected: false,
});

const scanWith = (findings: Finding[], over: Partial<ScanResult> = {}): ScanResult => ({
  session_id: "session-abcdefghijkl",
  kind: "pdf",
  file_name: "statement.pdf",
  pages: [{ page: 1, width: 595, height: 842, source: "text" }],
  findings,
  warnings: [],
  ai: null,
  ...over,
});

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

type Handler = (init?: RequestInit) => Response | Promise<Response>;

/** Route fetch calls by "METHOD path-fragment" or "path-fragment" keys (longest match wins). */
function mockFetch(routes: Record<string, Handler>) {
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? "GET").toUpperCase();
    const keys = Object.keys(routes)
      .filter((k) => {
        const [m, p] = k.includes(" ") ? k.split(" ") : [null, k];
        return url.includes(p) && (!m || m === method);
      })
      .sort((a, b) => b.length - a.length);
    if (!keys.length) return new Response(null, { status: 204 });
    return routes[keys[0]](init);
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

const pdfFile = () => new File(["%PDF-1.7 synthetic"], "statement.pdf", { type: "application/pdf" });

async function upload(file: File) {
  const user = userEvent.setup({ applyAccept: false });
  await user.upload(screen.getByLabelText(/upload a pdf/i), file);
  return user;
}

beforeEach(() => {
  localStorage.clear();
});

describe("Landing page", () => {
  it("shows the hero, upload card, limits and privacy, with no login", async () => {
    mockFetch({ "/api/health": () => json(healthWith()) });
    render(<App />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Find the hidden.Protect the personal.");
    expect(screen.getByRole("button", { name: /browse files/i })).toBeInTheDocument();
    expect(await screen.findByText(/up to 10 MB/i)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /built so your documents stay yours/i })).toBeInTheDocument();
    expect(screen.getAllByText(/processed on your computer/i).length).toBeGreaterThan(0);
    expect(screen.queryByText(/log in|sign up/i)).not.toBeInTheDocument();
  });

  it("disables the AI toggle and explains why when the model is unavailable", async () => {
    mockFetch({ "/api/health": () => json(healthWith()) });
    render(<App />);
    const toggle = await screen.findByRole("switch", { name: /contextual ai detection/i });
    await waitFor(() => expect(toggle).toBeDisabled());
    expect(screen.getByText(/ollama is not reachable/i)).toBeInTheDocument();
  });

  it("enables the AI toggle and says text stays on this computer for a local model", async () => {
    mockFetch({ "/api/health": () => json(healthWith({ ai: aiOn })) });
    render(<App />);
    const toggle = await screen.findByRole("switch", { name: /contextual ai detection/i });
    await waitFor(() => expect(toggle).toBeEnabled());
    expect(toggle).toBeChecked();
    expect(screen.getByText(/text never leaves the machine/i)).toBeInTheDocument();
    await userEvent.click(toggle);
    expect(toggle).not.toBeChecked();
    expect(localStorage.getItem("sherlock.ai-enabled")).toBe("off");
  });

  it("warns that text is sent elsewhere for a remote AI provider", async () => {
    mockFetch({ "/api/health": () => json(healthWith({ ai: { ...aiOn, is_local: false, endpoint_host: "ai.example.com" } })) });
    render(<App />);
    expect(await screen.findByText(/extracted text is sent to ai\.example\.com/i)).toBeInTheDocument();
  });

  it("uses hosted privacy wording when deployed", async () => {
    mockFetch({ "/api/health": () => json(healthWith({ deployment: "hosted", session_ttl_minutes: 15 })) });
    render(<App />);
    expect(await screen.findByText(/processed on the sherlock server/i)).toBeInTheDocument();
    expect(screen.getAllByText(/15 minutes/i).length).toBeGreaterThan(0);
    expect(screen.queryByText(/processed on your computer/i)).not.toBeInTheDocument();
  });

  it("rejects unsupported files before uploading", async () => {
    const fetchMock = mockFetch({ "/api/health": () => json(healthWith()) });
    render(<App />);
    await upload(new File(["hello"], "notes.txt", { type: "text/plain" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/unsupported file type/i);
    expect(fetchMock).not.toHaveBeenCalledWith(expect.stringContaining("/api/scan"), expect.anything());
  });

  it("explains when the backend is not running", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("Failed to fetch"))));
    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/can't reach its backend/i);
  });
});

describe("Scanning and review", () => {
  it("shows processing status, then masked findings and a summary", async () => {
    let finish: (r: Response) => void = () => undefined;
    mockFetch({
      "/api/health": () => json(healthWith()),
      "/api/scan": () => new Promise<Response>((resolve) => (finish = resolve)),
    });
    render(<App />);
    await upload(pdfFile());
    expect(await screen.findByRole("heading", { name: /scanning your file/i })).toBeInTheDocument();
    expect(screen.getByText(/uploading and reading the file/i)).toBeInTheDocument();

    finish(json(scanWith([finding({}), finding({ id: "f2", category: "pan", label: "Possible PAN", risk: "high", masked: "*******34F", value: "ABCPE1234F" })])));
    expect(await screen.findByRole("heading", { name: /2 possible findings/i })).toBeInTheDocument();
    expect(screen.getByText("ja***@example.com")).toBeInTheDocument();
    expect(screen.queryByText("jane.doe@example.com")).not.toBeInTheDocument();
    expect(screen.getAllByText("High risk")).toHaveLength(2); // summary tile + badge
    expect(screen.getByText(/text layer found, so ocr was not needed/i)).toBeInTheDocument();
    const summary = screen.getByRole("heading", { name: /results summary/i }).parentElement!;
    expect(within(summary).getByText("Rule-based").nextSibling).toHaveTextContent("2");
  });

  it("supports reveal, filters, select all and deselect all", async () => {
    mockFetch({
      "/api/health": () => json(healthWith()),
      "/api/scan": () => json(scanWith([finding({}), finding({ id: "f2", default_selected: false }), aiFinding])),
    });
    render(<App />);
    const user = await upload(pdfFile());
    await screen.findByRole("heading", { name: /3 possible findings/i });

    expect(screen.getByText(/1 of 3 selected/i)).toBeInTheDocument();
    await user.click(screen.getAllByRole("button", { name: /reveal email address/i })[0]);
    expect(screen.getByText("jane.doe@example.com")).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: /ai/i }));
    expect(screen.getAllByRole("checkbox")).toHaveLength(1);
    await user.click(screen.getByRole("tab", { name: /all/i }));

    await user.click(screen.getByRole("button", { name: /^deselect all$/i }));
    expect(screen.getByText(/0 of 3 selected/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /review & redact/i })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: /^select all$/i }));
    expect(screen.getByText(/3 of 3 selected/i)).toBeInTheDocument();
  });

  it("shows an empty state when nothing is found", async () => {
    mockFetch({ "/api/health": () => json(healthWith()), "/api/scan": () => json(scanWith([])) });
    render(<App />);
    await upload(pdfFile());
    expect(await screen.findByRole("heading", { name: /no sensitive information found/i })).toBeInTheDocument();
    expect(screen.getByText(/signatures, faces, handwriting/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /review & redact/i })).not.toBeInTheDocument();
  });

  it("marks findings that cannot be located and disables them", async () => {
    mockFetch({
      "/api/health": () => json(healthWith()),
      "/api/scan": () => json(scanWith([finding({ locatable: false, boxes: [], default_selected: false })])),
    });
    render(<App />);
    await upload(pdfFile());
    await screen.findByRole("heading", { name: /1 possible finding/i });
    expect(screen.getByRole("checkbox")).toBeDisabled();
    expect(screen.getByText(/location on the page could not be determined/i)).toBeInTheDocument();
  });

  it("reads pending pages with in-browser OCR and submits the words", async () => {
    const pending = scanWith([], { kind: "image", file_name: "shot.png", pages: [{ page: 1, width: 400, height: 200, source: "pending" }] });
    const fetchMock = mockFetch({
      "/api/health": () => json(healthWith({ ocr_available: false })),
      "/api/scan": () => json(pending),
      "/ocr-image/1": () => new Response(new Blob(["png"]), { status: 200 }),
      "POST /ocr": () =>
        json(scanWith([finding({ source: "ocr" })], { kind: "image", file_name: "shot.png", pages: [{ page: 1, width: 400, height: 200, source: "ocr" }] })),
    });
    render(<App />);
    await upload(new File(["png"], "shot.png", { type: "image/png" }));
    expect(await screen.findByText(/read 1 page in your browser/i)).toBeInTheDocument();
    expect(await screen.findByText("ja***@example.com")).toBeInTheDocument();
    const call = fetchMock.mock.calls.find(([url, init]) => String(url).endsWith("/ocr") && init?.method === "POST");
    const body = JSON.parse(String(call?.[1]?.body));
    expect(body.pages[0].words[1].text).toBe("jane.doe@example.com");
  });
});

describe("AI analysis", () => {
  it("runs automatically, polls progress, and adds unselected AI suggestions", async () => {
    let polls = 0;
    mockFetch({
      "/api/health": () => json(healthWith({ ai: aiOn })),
      "/api/scan": () => json(scanWith([finding({})])),
      "POST /ai": () => json(scanWith([finding({})], { ai: { state: "running", chunks_total: 1, chunks_done: 0, added: 0, confirmed: 0, rejected: 0, truncated: false, message: "", elapsed_seconds: 4 } })),
      "GET /ai": () => {
        polls += 1;
        return json(
          scanWith([finding({ origin: "rule+ai", ai_reason: "Contact email" }), aiFinding], {
            ai: { state: "done", chunks_total: 1, chunks_done: 1, added: 1, confirmed: 1, rejected: 0, truncated: false, message: "1 new suggestion(s); 1 rule finding(s) confirmed.", elapsed_seconds: 63 },
          }),
        );
      },
    });
    render(<App />);
    const user = await upload(pdfFile());
    expect(await screen.findByText(/analysing part 1 of 1 with qwen3:4b · 4s elapsed/i)).toBeInTheDocument();
    expect(await screen.findByText("A*** E******", {}, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.getByText(/(1m 03s)/)).toBeInTheDocument();
    expect(polls).toBeGreaterThan(0);
    expect(screen.getByText(/1 new suggestion/i)).toBeInTheDocument();
    expect(screen.getByText("AI suggestion")).toBeInTheDocument();
    expect(screen.getByText("Rule + AI")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: /personal identifier/i })).not.toBeChecked();
    expect(screen.getByText(/1 of 2 selected/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /select ai suggestions/i }));
    expect(screen.getByRole("checkbox", { name: /personal identifier/i })).toBeChecked();
  });

  it("does not run AI when the user turned it off, but offers to run it", async () => {
    localStorage.setItem("sherlock.ai-enabled", "off");
    const fetchMock = mockFetch({
      "/api/health": () => json(healthWith({ ai: aiOn })),
      "/api/scan": () => json(scanWith([finding({})])),
    });
    render(<App />);
    await upload(pdfFile());
    await screen.findByRole("heading", { name: /1 possible finding/i });
    expect(screen.getByText(/turned off\. you can still run it/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /run ai analysis/i })).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/ai"))).toBe(false);
  });

  it("reports AI failure honestly while rule findings stay usable", async () => {
    mockFetch({
      "/api/health": () => json(healthWith({ ai: aiOn })),
      "/api/scan": () => json(scanWith([finding({})])),
      "POST /ai": () => json(scanWith([finding({})], { ai: { state: "failed", chunks_total: 1, chunks_done: 1, added: 0, confirmed: 0, rejected: 0, truncated: false, message: "The AI model did not return usable results.", elapsed_seconds: 9 } })),
    });
    render(<App />);
    await upload(pdfFile());
    expect(await screen.findByText(/did not return usable results/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /retry ai analysis/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /review & redact/i })).toBeEnabled();
  });
});

describe("Redaction", () => {
  it("confirms, redacts only selected findings, and shows the download", async () => {
    const fetchMock = mockFetch({
      "/api/health": () => json(healthWith()),
      "/api/scan": () => json(scanWith([finding({}), finding({ id: "f2" })])),
      "/api/redact": () =>
        json({
          download_token: "tok_abcdefghijklmnopqrstuvwxyz012345",
          file_name: "statement-sherlock-redacted.pdf",
          media_type: "application/pdf",
          page_count: 1,
          redacted_count: 1,
          checks: ["Selected text removed from the PDF content (not just covered)"],
        }),
    });
    render(<App />);
    const user = await upload(pdfFile());
    await screen.findByRole("heading", { name: /2 possible findings/i });

    const [, second] = screen.getAllByRole("checkbox");
    await user.click(second);
    await user.click(screen.getByRole("button", { name: /review & redact/i }));
    const dialog = screen.getByRole("dialog", { name: /redact 1 item/i });
    expect(within(dialog).getByText(/original file is not changed/i)).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("/api/redact"))).toBe(false);

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /review & redact/i }));
    await user.click(screen.getByRole("button", { name: /redact permanently/i }));

    expect(await screen.findByRole("heading", { name: /redacted copy ready/i })).toBeInTheDocument();
    const call = fetchMock.mock.calls.find(([url]) => String(url).includes("/api/redact"));
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ session_id: "session-abcdefghijkl", finding_ids: ["f1"] });
    expect(screen.getByRole("link", { name: /download redacted file/i })).toHaveAttribute(
      "href",
      "/api/download/tok_abcdefghijklmnopqrstuvwxyz012345",
    );
    expect(screen.getByText(/original · not modified/i)).toBeInTheDocument();
    expect(screen.getByText(/redacted · pdf · 1 page/i)).toBeInTheDocument();
    expect(screen.getByText(/check the file before you share it/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /start over/i }));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith("/api/session/session-abcdefghijkl", expect.objectContaining({ method: "DELETE" })),
    );
    expect(screen.getByRole("button", { name: /browse files/i })).toBeInTheDocument();
  });

  it("shows backend errors from scanning and from redaction", async () => {
    let scanCount = 0;
    mockFetch({
      "/api/health": () => json(healthWith()),
      "/api/scan": () => {
        scanCount += 1;
        return scanCount === 1
          ? json({ error: { code: "password_protected", message: "This PDF is password-protected." } }, 422)
          : json(scanWith([finding({})]));
      },
      "/api/redact": () =>
        json({ error: { code: "redaction_verification_failed", message: "Sherlock could not confirm removal." } }, 500),
    });
    render(<App />);
    const user = await upload(pdfFile());
    expect(await screen.findByRole("alert")).toHaveTextContent(/password-protected/i);

    await user.upload(screen.getByLabelText(/upload a pdf/i), pdfFile());
    await screen.findByRole("heading", { name: /1 possible finding/i });
    await user.click(screen.getByRole("button", { name: /review & redact/i }));
    await user.click(screen.getByRole("button", { name: /redact permanently/i }));
    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText(/could not confirm removal/i)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /download/i })).not.toBeInTheDocument();
  });
});
