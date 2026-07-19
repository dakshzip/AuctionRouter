"""AuctionRouter eval harness.

Runs the bucketed dataset through the pipeline (or a baseline), scores every
answer with an independent LLM judge, and reports quality / routing / cost /
latency per bucket.

Usage (from backend/):

    # full pipeline, cheap frontier stand-in (recommended for iteration)
    FRONTIER_MODEL_ID=deepseek/deepseek-r1 uv run python -m evals.run_evals

    # frontier-only baseline (what "just use the big model" would cost/score)
    FRONTIER_MODEL_ID=deepseek/deepseek-r1 uv run python -m evals.run_evals --mode frontier

    # quick smoke run
    uv run python -m evals.run_evals --limit 5

    # one bucket
    uv run python -m evals.run_evals --bucket stem_hard

Results land in evals/results/<timestamp>-<mode>.json; a summary table prints
to stdout. Modes: auction (default, full pipeline) | frontier (every query
straight to the tier-2 model).
"""

import argparse
import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from app import prompts
from app.config import TIER2_MODEL, VERIFIER_MODEL, settings
from app.llm import chat, close_client, extract_json
from app.pipeline import run_query

DATASET = Path(__file__).parent / "dataset.jsonl"
RESULTS_DIR = Path(__file__).parent / "results"

JUDGE_SYSTEM = """You are grading an assistant's answer to a user query.
You may be given REFERENCE notes describing what a correct answer contains —
they are hints for you, not a script the answer must recite.

Score 0.0-1.0:
- 1.0: correct and complete; for subjective/ambiguous queries, a reasonable,
  relevant, well-organized answer earns 1.0.
- 0.7: right but with real gaps or minor errors.
- 0.4: partially right; core of the question not properly delivered.
- 0.0: wrong, off-topic, a refusal, or a request for clarification.

Judge only correctness/completeness, not style or length.
Respond with ONLY a JSON object:
{"score": <0.0-1.0>, "reason": "<one sentence>"}"""


def _clamp(x) -> float:
    try:
        return max(0.0, min(1.0, float(x)))
    except (TypeError, ValueError):
        return 0.0


async def judge(item: dict, answer: str) -> tuple[float | None, str]:
    ref = (f"\n\nREFERENCE NOTES:\n{item['reference']}"
           if item.get("reference") else "")
    user = f"QUERY:\n{item['query']}{ref}\n\nANSWER TO GRADE:\n{answer}"
    try:
        resp = await chat(VERIFIER_MODEL, JUDGE_SYSTEM, user,
                          reasoning_effort="low")
        data = extract_json(resp.content)
        return _clamp(data.get("score")), str(data.get("reason", ""))[:200]
    except Exception as e:  # judge failure shouldn't sink the run
        return None, f"judge error: {e}"[:200]


async def eval_item(sem: asyncio.Semaphore, mode: str, item: dict) -> dict:
    async with sem:
        start = time.monotonic()
        try:
            if mode == "frontier":
                resp = await chat(TIER2_MODEL, prompts.FRONTIER_SYSTEM,
                                  item["query"],
                                  max_tokens=settings.max_frontier_tokens,
                                  reasoning_effort=settings.frontier_reasoning_effort)
                answer = resp.content
                out = {
                    "tier": 2, "escalated": True,
                    "cost_usd": TIER2_MODEL.estimate_cost(
                        resp.tokens_in, resp.tokens_out, resp.served_model),
                    "latency_ms": int((time.monotonic() - start) * 1000),
                    "answered_by": TIER2_MODEL.display_name,
                    "verification": None,
                }
            else:
                run = await run_query(item["query"],
                                      hint=item.get("hint", "general"))
                answer = run.answer
                out = {
                    "tier": run.tier, "escalated": run.escalated,
                    "cost_usd": run.total_cost_usd,
                    "latency_ms": run.latency_ms,
                    "answered_by": run.answered_by,
                    "verification": (run.verification.score
                                     if run.verification else None),
                }
        except Exception as e:
            return {**item, "error": str(e)[:300], "judge_score": 0.0,
                    "judge_reason": "pipeline error"}

        score, reason = await judge(item, answer)
        return {
            **item, **out,
            "answer": answer,
            "judge_score": score,
            "judge_reason": reason,
            "routed_as_expected": out["tier"] == item["expect_tier"],
        }


def summarize(results: list[dict], mode: str) -> str:
    def agg(rows: list[dict]) -> dict:
        scored = [r["judge_score"] for r in rows
                  if r.get("judge_score") is not None]
        return {
            "n": len(rows),
            "judge": round(sum(scored) / len(scored), 3) if scored else None,
            "tier1%": round(100 * sum(1 for r in rows if r.get("tier") == 1)
                            / len(rows)),
            "routed%": round(100 * sum(1 for r in rows
                                       if r.get("routed_as_expected"))
                             / len(rows)),
            "p50_ms": sorted(r.get("latency_ms", 0)
                             for r in rows)[len(rows) // 2],
            "cost$": round(sum(r.get("cost_usd", 0) for r in rows), 4),
        }

    lines = [f"\n=== {mode} | frontier={TIER2_MODEL.openrouter_id} "
             f"| {len(results)} items ==="]
    header = f"{'bucket':<14}{'n':>3}{'judge':>7}{'tier1%':>8}{'routed%':>9}{'p50 ms':>8}{'cost $':>9}"
    lines.append(header)
    buckets = sorted({r["bucket"] for r in results})
    for b in buckets + ["OVERALL"]:
        rows = results if b == "OVERALL" else [r for r in results
                                               if r["bucket"] == b]
        a = agg(rows)
        lines.append(f"{b:<14}{a['n']:>3}{str(a['judge']):>7}{a['tier1%']:>7}%"
                     f"{a['routed%']:>8}%{a['p50_ms']:>8}{a['cost$']:>9}")
    errors = [r for r in results if r.get("error")]
    if errors:
        lines.append(f"errors: {len(errors)} -> " +
                     ", ".join(r["id"] for r in errors))
    return "\n".join(lines)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["auction", "frontier"],
                    default="auction")
    ap.add_argument("--bucket", default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--concurrency", type=int, default=3)
    args = ap.parse_args()

    items = [json.loads(line) for line in DATASET.read_text().splitlines()
             if line.strip()]
    if args.bucket:
        items = [i for i in items if i["bucket"] == args.bucket]
    if args.limit:
        items = items[:args.limit]

    sem = asyncio.Semaphore(args.concurrency)
    results = await asyncio.gather(
        *(eval_item(sem, args.mode, i) for i in items))
    results = list(results)

    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_path = RESULTS_DIR / f"{stamp}-{args.mode}.json"
    out_path.write_text(json.dumps(
        {"mode": args.mode, "frontier": TIER2_MODEL.openrouter_id,
         "results": results}, indent=1))

    print(summarize(results, args.mode))
    print(f"\nfull results: {out_path}")
    await asyncio.sleep(1)  # let fire-and-forget save_run tasks settle
    await close_client()


if __name__ == "__main__":
    asyncio.run(main())
