"""A tiny model that answers one question: does this query need a web search?

Runs at t=0 alongside the hedge and the bids, not before them. That ordering is
load-bearing: the gate's TTFT (~450-500ms measured) is roughly the same as the
hedge model's, so putting it on the critical path would double time-to-first-
token on the majority of queries, which need no web search at all. In parallel
it costs nothing and simply cancels the hedge far earlier than the bidders
would have (~500ms instead of 2-4s).

It exists because the regex it supplements has poor recall on natural
phrasing — 62.5% on held-out queries against this model's 100%. See
evals/bench_web_gate.py for the comparison and how the model was chosen.
"""

import asyncio
import logging

from .config import WEB_GATE_MODEL, settings
from .llm import LLMError, chat
from .schemas import Usage

log = logging.getLogger(__name__)

# Every token here is on a latency-critical path, so the prompt stays short.
# Identical to the one the benchmark scored, so measured accuracy carries over.
GATE_SYSTEM = (
    "You decide if a user query needs a live web search to answer correctly.\n"
    "Answer YES if it needs current, real-time, or post-training information: "
    "news, prices, scores, weather, releases, results, who currently holds a "
    "role, or a specific named item you may not know.\n"
    "Answer NO for timeless questions: math, code, definitions, writing, "
    "advice, explanations, general knowledge.\n"
    "Reply with exactly one word: YES or NO."
)


def enabled() -> bool:
    return bool(settings.web_gate_enabled and settings.openrouter_api_key)


async def decide(query: str) -> tuple[bool | None, Usage | None]:
    """Return (needs_web, usage). None means "no opinion" — never a guess.

    Callers must treat None as "fall back to the other signals" rather than
    as False, so a gate outage can only lose recall, never invent it.
    """
    if not enabled() or not query.strip():
        return None, None
    try:
        resp = await asyncio.wait_for(
            chat(WEB_GATE_MODEL, GATE_SYSTEM, query,
                 max_tokens=8, prefer_paid=True),
            timeout=settings.web_gate_timeout_s,
        )
    except (LLMError, asyncio.TimeoutError, Exception) as e:
        log.warning("web gate failed: %s: %s", type(e).__name__, str(e)[:150])
        return None, None

    usage = Usage(
        model_key=WEB_GATE_MODEL.key,
        model_name=WEB_GATE_MODEL.display_name,
        stage="gate",
        tokens_in=resp.tokens_in,
        tokens_out=resp.tokens_out,
        cost_usd=WEB_GATE_MODEL.estimate_cost(resp.tokens_in, resp.tokens_out,
                                              resp.served_model),
        latency_ms=resp.latency_ms,
    )
    answer = resp.content.strip().upper()
    if answer.startswith("YES"):
        return True, usage
    if answer.startswith("NO"):
        return False, usage
    log.warning("web gate returned unparseable %r", resp.content[:60])
    return None, usage
