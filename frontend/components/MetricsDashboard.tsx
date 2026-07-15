"use client";

import { useEffect, useState } from "react";
import { fetchMetrics } from "@/lib/api";
import type { MetricsSummary } from "@/lib/types";
import { Bar, Card, Stat } from "./ui";

const MODEL_LABELS: Record<string, string> = {
  gemma: "Gemma 4 26B",
  deepseek: "DeepSeek",
  qwen: "Qwen3 Next 80B",
};

export function MetricsDashboard({ refreshKey }: { refreshKey: number }) {
  const [metrics, setMetrics] = useState<MetricsSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchMetrics()
      .then((m) => {
        setMetrics(m);
        setError(null);
      })
      .catch((e) => setError(String(e)));
  }, [refreshKey]);

  if (error)
    return (
      <p className="text-red-400">
        ✖ could not load metrics — is the backend running? ({error})
      </p>
    );
  if (!metrics) return <p className="text-stone-500">loading…</p>;
  if (metrics.total_queries === 0)
    return (
      <div className="border-2 border-dashed border-stone-700 p-6 text-center text-stone-500">
        ── NO SCORES YET ──
        <br />
        ask something in the chat tab to start collecting metrics
      </div>
    );

  const totalWins = Object.values(metrics.wins_by_model).reduce((a, b) => a + b, 0);

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat
          label="avg cost / query"
          value={`$${metrics.avg_cost_usd.toFixed(4)}`}
          sub={`total $${metrics.total_cost_usd.toFixed(4)}`}
        />
        <Stat
          label="saved vs boss-only"
          value={`$${metrics.total_saved_usd.toFixed(4)}`}
        />
        <Stat
          label="avg latency"
          value={`${(metrics.avg_latency_ms / 1000).toFixed(1)}s`}
        />
        <Stat
          label="tier-1 clears"
          value={`${Math.round(metrics.tier1_resolution_rate * 100)}%`}
          sub={`boss fights ${Math.round(metrics.escalation_rate * 100)}% · ${metrics.total_queries} queries`}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Auction wins">
          <div className="space-y-3">
            {Object.keys(MODEL_LABELS).map((key) => {
              const wins = metrics.wins_by_model[key] ?? 0;
              return (
                <div key={key}>
                  <div className="mb-1 flex justify-between text-sm">
                    <span className="text-stone-400">{MODEL_LABELS[key]}</span>
                    <span className="text-orange-400">{wins}</span>
                  </div>
                  <Bar value={totalWins ? wins / totalWins : 0} tone="sky" />
                </div>
              );
            })}
          </div>
        </Card>

        <Card title="Verification pass rate">
          <div className="space-y-3">
            {Object.keys(MODEL_LABELS).map((key) => {
              const acc = metrics.accuracy_by_model[key];
              return (
                <div key={key}>
                  <div className="mb-1 flex justify-between text-sm">
                    <span className="text-stone-400">{MODEL_LABELS[key]}</span>
                    <span className="text-green-400">
                      {acc === undefined ? "—" : `${Math.round(acc * 100)}%`}
                    </span>
                  </div>
                  <Bar value={acc ?? 0} tone="green" />
                </div>
              );
            })}
          </div>
        </Card>
      </div>
    </div>
  );
}
