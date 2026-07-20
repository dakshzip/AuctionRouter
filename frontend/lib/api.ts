import type { ChatTurn, MetricsSummary, RunResult } from "./types";

// Same origin in production (FastAPI serves the static export);
// the local backend during `next dev`. On Vercel this MUST be set to the
// backend (HF Space) URL, since the frontend and API are different origins.
const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ??
  (process.env.NODE_ENV === "development" ? "http://localhost:8000" : "");

// --- Access code (shared demo gate) -----------------------------------------
// Entered at runtime, kept in sessionStorage — never baked into the bundle.
const CODE_KEY = "ar_access_code";

export function getAccessCode(): string {
  if (typeof window === "undefined") return "";
  return window.sessionStorage.getItem(CODE_KEY) ?? "";
}
export function setAccessCode(code: string): void {
  window.sessionStorage.setItem(CODE_KEY, code);
}
export function clearAccessCode(): void {
  window.sessionStorage.removeItem(CODE_KEY);
}

let authFailureHandler: (() => void) | null = null;
export function onAuthFailure(fn: () => void): void {
  authFailureHandler = fn;
}
function handle401(): void {
  clearAccessCode();
  authFailureHandler?.();
}

function authHeaders(extra: Record<string, string> = {}): Record<string, string> {
  const code = getAccessCode();
  return code ? { ...extra, "X-Access-Code": code } : extra;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: authHeaders(init?.headers as Record<string, string>),
  });
  if (res.status === 401) {
    handle401();
    throw new Error("access code rejected");
  }
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`${res.status}: ${body.slice(0, 300)}`);
  }
  return res.json();
}

export function submitQuery(
  query: string,
  history: ChatTurn[] = [],
): Promise<RunResult> {
  return request<RunResult>("/api/query", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, history }),
  });
}

export interface StreamEvent {
  type: "stage" | "auction" | "token" | "reset" | "reasoning" | "verification" | "frontier_failed" | "error" | "done";
  stage?: "bidding" | "drafting" | "verifying" | "delivering" | "escalating";
  model?: string;
  text?: string;
  reason?: string | null;
  message?: string;
  score?: number;
  passed?: boolean;
  feedback?: string;
  winner?: string | null;
  verified?: boolean;
  escalated?: boolean;
  run?: RunResult;
}

export type QueryHint = "general" | "coding" | "reasoning";

// POST + NDJSON reader (EventSource is GET-only)
export async function streamQuery(
  query: string,
  history: ChatTurn[],
  hint: QueryHint,
  onEvent: (ev: StreamEvent) => void,
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/query/stream`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ query, history, hint }),
  });
  if (res.status === 401) {
    handle401();
    throw new Error("access code rejected");
  }
  if (!res.ok || !res.body) {
    const body = await res.text().catch(() => "");
    throw new Error(`${res.status}: ${body.slice(0, 300)}`);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let nl;
    while ((nl = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, nl).trim();
      buffer = buffer.slice(nl + 1);
      if (line) onEvent(JSON.parse(line) as StreamEvent);
    }
  }
}

// Open endpoint (no code) — tells the frontend whether to show the gate
export async function fetchHealth(): Promise<{ access_required: boolean }> {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) throw new Error(`${res.status}`);
  return res.json();
}

export function fetchMetrics(): Promise<MetricsSummary> {
  return request<MetricsSummary>("/api/metrics");
}

export function fetchRuns(limit = 50): Promise<RunResult[]> {
  return request<RunResult[]>(`/api/runs?limit=${limit}`);
}
