import type { RunResult } from "@/lib/types";
import { Badge, Bar, Card } from "./ui";

export function VerificationPanel({ run }: { run: RunResult }) {
  const v = run.verification;
  return (
    <Card title="Verification">
      {v ? (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="font-[family-name:var(--font-pixel)] text-xl text-orange-400">
              {v.score.toFixed(2)}
            </span>
            <Badge tone={v.passed ? "green" : "rose"}>
              {v.passed ? "✓ pass" : "✖ fail"}
            </Badge>
          </div>
          <Bar value={v.score} tone={v.passed ? "green" : "rose"} />
          <p className="text-sm text-stone-400">{v.feedback}</p>
          <p className="text-xs text-stone-600">pass threshold: 0.80</p>
        </div>
      ) : (
        <p className="text-sm text-stone-500">
          {run.escalated
            ? "skipped — escalated before a draft was produced"
            : "no verification data"}
        </p>
      )}
      {run.escalated && (
        <div className="mt-3 border-2 border-orange-600 bg-orange-950/40 p-3 shadow-[3px_3px_0_0_rgba(249,115,22,0.25)]">
          <div className="mb-1 flex items-center gap-2">
            <Badge tone="amber">⚔ boss fight</Badge>
            <span className="text-sm text-stone-400">→ {run.answered_by}</span>
          </div>
          <p className="text-sm text-orange-300/90">{run.escalation_reason}</p>
        </div>
      )}
    </Card>
  );
}
