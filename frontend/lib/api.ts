import type { MetricsSummary, RunResult } from "./types";

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

export function submitQuery(query: string): Promise<RunResult> {
  return request<RunResult>("/api/query", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });
}

export function fetchMetrics(): Promise<MetricsSummary> {
  return request<MetricsSummary>("/api/metrics");
}

export function fetchRuns(limit = 50): Promise<RunResult[]> {
  return request<RunResult[]>(`/api/runs?limit=${limit}`);
}
