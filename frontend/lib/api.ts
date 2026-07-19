import type { ChatTurn, MetricsSummary, RunResult } from "./types";

// Same origin in production (FastAPI serves the static export);
// the local backend during `next dev`.
const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ??
  (process.env.NODE_ENV === "development" ? "http://localhost:8000" : "");

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init);
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
  type: "stage" | "auction" | "token" | "reasoning" | "verification" | "frontier_failed" | "error" | "done";
  stage?: "bidding" | "drafting" | "verifying" | "delivering" | "escalating";
  model?: string;
  text?: string;
  reason?: string | null;
  message?: string;
  score?: number;
  passed?: boolean;
  feedback?: string;
  winner?: string | null;
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
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, history, hint }),
  });
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

export function fetchMetrics(): Promise<MetricsSummary> {
  return request<MetricsSummary>("/api/metrics");
}

export function fetchRuns(limit = 50): Promise<RunResult[]> {
  return request<RunResult[]>(`/api/runs?limit=${limit}`);
}
