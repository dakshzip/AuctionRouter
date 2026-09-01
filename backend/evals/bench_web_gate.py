"""Benchmark candidate models for the t=0 web-search gate.

The gate has to answer one yes/no question ("does this query need fresh
data?") before anything else runs, so the only latency that matters is time to
first token. A model that is accurate but takes 800ms is useless here: the
whole point is to decide before the speculative hedge would have started.

Ground truth is the labelled set already pinned in tests/test_web_heuristic.py,
so a model is scored against exactly the behaviour the regex is held to.

Usage:  uv run python evals/bench_web_gate.py [--models a,b,c] [--repeat 2]
"""

import argparse
import ast
import asyncio
import json
import os
import statistics
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BASE = "https://openrouter.ai/api/v1/chat/completions"

# Kept deliberately tiny: every token here is on the critical path.
SYSTEM = (
    "You decide if a user query needs a live web search to answer correctly.\n"
    "Answer YES if it needs current, real-time, or post-training information: "
    "news, prices, scores, weather, releases, results, who currently holds a "
    "role, or a specific named item you may not know.\n"
    "Answer NO for timeless questions: math, code, definitions, writing, "
    "advice, explanations, general knowledge.\n"
    "Reply with exactly one word: YES or NO."
)

CANDIDATES = [
    "amazon/nova-micro-v1",
    "google/gemma-3-4b-it",
    "meta-llama/llama-3.2-3b-instruct",
    "meta-llama/llama-3.1-8b-instruct",
    "inclusionai/ling-2.6-flash",
    "qwen/qwen3.7-flash",
    "ibm-granite/granite-4.0-h-micro",
    "mistralai/mistral-nemo",
    "openai/gpt-5-nano",
    "cohere/command-r7b-12-2024",
]


def load_heldout() -> list[tuple[str, bool]]:
    """Queries neither the regex nor its tests were built against."""
    d = json.loads((Path(__file__).resolve().parent
                    / "heldout_queries.json").read_text())
    return ([(q, True) for q in d["needs_web"]]
            + [(q, False) for q in d["no_web"]])


def score_regex(data: list[tuple[str, bool]]) -> tuple[float, list[str]]:
    """The incumbent, for comparison. Costs ~0ms, so it's the bar to beat."""
    from app.pipeline import _needs_web_heuristic
    correct, misses = 0, []
    for q, truth in data:
        if _needs_web_heuristic(q) == truth:
            correct += 1
        elif len(misses) < 8:
            misses.append(f"{'WEB' if truth else 'no'}: {q}")
    return correct / len(data), misses


def load_labelled() -> list[tuple[str, bool]]:
    """(query, needs_web) pairs from the heuristic's own test fixtures."""
    src = (Path(__file__).resolve().parent.parent
           / "tests" / "test_web_heuristic.py").read_text()
    tree = ast.parse(src)
    out: list[tuple[str, bool]] = []
    for node in tree.body:
        if not (isinstance(node, ast.Assign)
                and isinstance(node.value, ast.List)):
            continue
        name = node.targets[0].id
        if name not in ("NEEDS_WEB", "NO_WEB"):
            continue
        for el in node.value.elts:
            if isinstance(el, ast.Constant) and isinstance(el.value, str):
                out.append((el.value, name == "NEEDS_WEB"))
    return out


async def measure_gate_call(client: httpx.AsyncClient, model: str, query: str,
                key: str, max_tokens: int = 32,
                effort: str = "low") -> tuple[float | None, bool | None]:
    """One streamed call. Returns (ttft_ms, answered_yes).

    max_tokens/effort are tunable because reasoning models spend the budget
    thinking before any content appears: gpt-5-nano emits 400-1400 reasoning
    tokens at default effort, so a small cap returns nothing at all.
    """
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": query},
        ],
        "max_tokens": max_tokens,
        "temperature": 0,
        "stream": True,
        # Route to the fastest provider, matching how the app already routes
        "provider": {"sort": "latency"},
        # Thinking tokens would dominate TTFT; off wherever supported
        "reasoning": {"effort": effort, "exclude": True},
    }
    start = time.monotonic()
    ttft = None
    text = ""
    try:
        async with client.stream(
            "POST", BASE, json=body,
            headers={"Authorization": f"Bearer {key}"}, timeout=45,
        ) as r:
            if r.status_code != 200:
                return None, None
            async for line in r.aiter_lines():
                if not line.startswith("data: "):
                    continue
                payload = line[6:].strip()
                if payload == "[DONE]":
                    break
                try:
                    d = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                ch = (d.get("choices") or [{}])[0]
                # Some providers stream deltas, others send the whole message
                # in one non-delta chunk; accept either or they score as zero.
                piece = ((ch.get("delta") or {}).get("content")
                         or (ch.get("message") or {}).get("content")
                         or ch.get("text") or "")
                if piece:
                    if ttft is None:
                        ttft = (time.monotonic() - start) * 1000
                    text += piece
    except Exception:
        return None, None
    up = text.strip().upper()
    yes = True if up.startswith("YES") else False if up.startswith("NO") else None
    return ttft, yes


async def bench(model: str, data: list[tuple[str, bool]], key: str,
                repeat: int, max_tokens: int = 32,
                effort: str = "low") -> dict:
    ttfts: list[float] = []
    correct = wrong = unparsed = failed = 0
    misses: list[str] = []
    async with httpx.AsyncClient() as client:
        for _ in range(repeat):
            for q, truth in data:
                ttft, yes = await measure_gate_call(client, model, q, key,
                                        max_tokens, effort)
                if ttft is None:
                    failed += 1
                    continue
                ttfts.append(ttft)
                if yes is None:
                    unparsed += 1
                elif yes == truth:
                    correct += 1
                else:
                    wrong += 1
                    if len(misses) < 6:
                        misses.append(f"{'WEB' if truth else 'no'}: {q}")
    graded = correct + wrong + unparsed
    return {
        "model": model,
        "n": graded,
        "acc": correct / graded if graded else 0.0,
        "p50": statistics.median(ttfts) if ttfts else None,
        "p95": (statistics.quantiles(ttfts, n=20)[18]
                if len(ttfts) >= 20 else (max(ttfts) if ttfts else None)),
        "failed": failed,
        "unparsed": unparsed,
        "misses": misses,
    }


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default=",".join(CANDIDATES))
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--limit", type=int, default=0, help="cap queries, for smoke runs")
    ap.add_argument("--max-tokens", type=int, default=32,
                    help="raise for reasoning models, which spend the budget "
                         "thinking before emitting any content")
    ap.add_argument("--effort", default="low",
                    help="reasoning effort; 'minimal' skips thinking on gpt-5*")
    ap.add_argument("--dataset", choices=["pinned", "heldout"], default="heldout",
                    help="'pinned' is the regex's own test set (it scores 100%% "
                         "there by construction); 'heldout' is the fair test")
    args = ap.parse_args()

    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parent.parent / ".env")
        key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        raise SystemExit("OPENROUTER_API_KEY not set")

    data = load_labelled() if args.dataset == "pinned" else load_heldout()
    if args.limit:
        data = data[: args.limit]
    print(f"{len(data)} {args.dataset} queries x{args.repeat}\n")

    acc, misses = score_regex(data)
    print(f"{'[incumbent] regex _needs_web_heuristic':42} acc {acc:5.1%}  "
          f"ttft ~0ms (no API call)")
    for m in misses:
        print(f"          miss -> {m}")
    print()

    results = []
    for model in args.models.split(","):
        r = await bench(model.strip(), data, key, args.repeat,
                        args.max_tokens, args.effort)
        results.append(r)
        p50 = f"{r['p50']:6.0f}" if r["p50"] else "   n/a"
        p95 = f"{r['p95']:6.0f}" if r["p95"] else "   n/a"
        print(f"{r['model']:42} acc {r['acc']:5.1%}  "
              f"ttft p50 {p50}ms  p95 {p95}ms  "
              f"fail {r['failed']:2}  unparsed {r['unparsed']:2}")

    print("\n--- ranked by p50 TTFT among models at >=90% accuracy ---")
    good = [r for r in results if r["acc"] >= 0.90 and r["p50"]]
    for r in sorted(good, key=lambda r: r["p50"]):
        print(f"{r['p50']:6.0f}ms  {r['acc']:5.1%}  {r['model']}")
        for m in r["misses"]:
            print(f"          miss -> {m}")
    if not good:
        print("(none reached 90%)")


if __name__ == "__main__":
    asyncio.run(main())
