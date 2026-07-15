"""The AuctionRouter LangGraph pipeline.

    bid_collection -> auction -> (escalate | draft) -> verify -> (escalate | finalize)

Bids are gathered in parallel from all tier-1 models. The auction node scores
them (0.7*confidence + 0.2*historical_accuracy - 0.1*cost) and either picks a
winner or escalates immediately on low confidence / high disagreement. The
verifier gates the draft; failures escalate to the frontier model.
"""

import asyncio
import statistics
import time
import uuid
from typing import Optional, TypedDict

from langgraph.graph import END, StateGraph

from . import prompts
from .config import BASELINE_MODEL, TIER1_MODELS, TIER2_MODEL, VERIFIER_MODEL, settings
from .llm import LLMError, chat, extract_json
from .schemas import Bid, RunResult, Usage, Verification
from .store import get_store


class RouterState(TypedDict, total=False):
    query: str
    bids: list[Bid]
    winner: Optional[str]
    draft_answer: Optional[str]
    verification: Optional[Verification]
    escalated: bool
    escalation_reason: Optional[str]
    final_answer: str
    answered_by: str
    tier: int
    usages: list[Usage]
    started_at: float


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


async def _get_bid(model_key: str, query: str, history: dict[str, float]) -> tuple[Bid, Optional[Usage]]:
    spec = TIER1_MODELS[model_key]
    hist = history.get(model_key, settings.default_historical_accuracy)
    try:
        resp = await chat(spec, prompts.BID_SYSTEM, prompts.bid_user(query),
                          timeout=settings.bid_timeout_s,
                          max_tokens=settings.max_bid_tokens)
        data = extract_json(resp.content)
        bid = Bid(
            model_key=model_key,
            model_name=spec.display_name,
            confidence=_clamp(data.get("confidence", 0)),
            estimated_difficulty=_clamp(data.get("estimated_difficulty", 0.5)),
            reason=str(data.get("reason", ""))[:300],
            historical_accuracy=hist,
        )
        usage = Usage(
            model_key=model_key, model_name=spec.display_name, stage="bid",
            tokens_in=resp.tokens_in, tokens_out=resp.tokens_out,
            cost_usd=spec.estimate_cost(resp.tokens_in, resp.tokens_out),
            latency_ms=resp.latency_ms,
        )
        return bid, usage
    except (LLMError, ValueError, asyncio.TimeoutError, Exception) as e:
        return Bid(model_key=model_key, model_name=spec.display_name,
                   confidence=0.0, reason="bid failed",
                   historical_accuracy=hist, error=str(e)[:200]), None


async def bid_collection(state: RouterState) -> RouterState:
    history = await get_store().historical_accuracy()
    results = await asyncio.gather(
        *(_get_bid(key, state["query"], history) for key in TIER1_MODELS)
    )
    bids = [b for b, _ in results]
    usages = [u for _, u in results if u is not None]

    # Normalize per-model output cost to 0..1 for the auction's cost term
    costs = {k: m.cost_per_mtok_out for k, m in TIER1_MODELS.items()}
    max_cost = max(costs.values()) or 1.0
    for bid in bids:
        bid.cost_factor = costs[bid.model_key] / max_cost
        bid.auction_score = round(
            settings.auction_w_confidence * bid.confidence
            + settings.auction_w_history * bid.historical_accuracy
            - settings.auction_w_cost * bid.cost_factor,
            4,
        )
    return {"bids": bids, "usages": state.get("usages", []) + usages}


async def auction(state: RouterState) -> RouterState:
    bids = state["bids"]
    valid = [b for b in bids if b.error is None]
    if not valid:
        return {"escalated": True, "escalation_reason": "All tier-1 bidders failed"}

    confidences = [b.confidence for b in valid]
    max_conf = max(confidences)
    if max_conf < settings.min_auction_confidence:
        return {"escalated": True,
                "escalation_reason": f"Low auction confidence (max {max_conf:.2f} < {settings.min_auction_confidence})"}

    if len(confidences) >= 2:
        spread = statistics.pstdev(confidences)
        if spread > settings.disagreement_stddev:
            return {"escalated": True,
                    "escalation_reason": f"Strong model disagreement (stddev {spread:.2f} > {settings.disagreement_stddev})"}

    winner = max(valid, key=lambda b: b.auction_score)
    return {"winner": winner.model_key, "escalated": False}


async def draft(state: RouterState) -> RouterState:
    spec = TIER1_MODELS[state["winner"]]
    try:
        resp = await chat(spec, prompts.ANSWER_SYSTEM, state["query"])
    except LLMError as e:
        return {"escalated": True, "escalation_reason": f"Winner failed to answer: {str(e)[:150]}"}
    if not resp.content.strip():
        return {"escalated": True,
                "escalation_reason": f"{spec.display_name} returned an empty draft"}
    usage = Usage(
        model_key=spec.key, model_name=spec.display_name, stage="draft",
        tokens_in=resp.tokens_in, tokens_out=resp.tokens_out,
        cost_usd=spec.estimate_cost(resp.tokens_in, resp.tokens_out),
        latency_ms=resp.latency_ms,
    )
    return {"draft_answer": resp.content, "usages": state["usages"] + [usage]}


async def verify(state: RouterState) -> RouterState:
    try:
        resp = await chat(VERIFIER_MODEL, prompts.VERIFY_SYSTEM,
                          prompts.verify_user(state["query"], state["draft_answer"]))
        data = extract_json(resp.content)
        score = _clamp(data.get("score", 0))
        verification = Verification(
            score=score,
            passed=bool(data.get("pass", score >= settings.verification_threshold)),
            feedback=str(data.get("feedback", ""))[:500],
        )
    except (LLMError, ValueError) as e:
        # If the verifier itself breaks, fail safe: escalate
        verification = Verification(score=0.0, passed=False,
                                    feedback=f"Verifier error: {str(e)[:150]}")
        resp = None

    usages = state["usages"]
    if resp is not None:
        usages = usages + [Usage(
            model_key=VERIFIER_MODEL.key, model_name=VERIFIER_MODEL.display_name,
            stage="verify", tokens_in=resp.tokens_in, tokens_out=resp.tokens_out,
            cost_usd=VERIFIER_MODEL.estimate_cost(resp.tokens_in, resp.tokens_out),
            latency_ms=resp.latency_ms,
        )]

    out: RouterState = {"verification": verification, "usages": usages}
    if verification.score < settings.verification_threshold or not verification.passed:
        out["escalated"] = True
        out["escalation_reason"] = (
            f"Verification failed (score {verification.score:.2f} < {settings.verification_threshold})"
        )
    return out


async def escalate(state: RouterState) -> RouterState:
    try:
        resp = await chat(TIER2_MODEL, prompts.ANSWER_SYSTEM, state["query"],
                          max_tokens=settings.max_frontier_tokens,
                          reasoning_effort="low")
        if not resp.content.strip():
            raise LLMError(f"{TIER2_MODEL.openrouter_id}: empty response "
                           "(reasoning consumed the token budget)")
    except LLMError as e:
        # Frontier unavailable (rate limit, credits, outage): fall back to the
        # tier-1 draft if we have one rather than failing the whole request.
        if state.get("draft_answer"):
            spec = TIER1_MODELS[state["winner"]]
            return {
                "final_answer": state["draft_answer"],
                "answered_by": f"{spec.display_name} (frontier unavailable)",
                "tier": 1,
                "escalation_reason": (state.get("escalation_reason") or "")
                + f" | frontier failed: {str(e)[:150]}",
            }
        raise
    usage = Usage(
        model_key=TIER2_MODEL.key, model_name=TIER2_MODEL.display_name,
        stage="escalate", tokens_in=resp.tokens_in, tokens_out=resp.tokens_out,
        cost_usd=TIER2_MODEL.estimate_cost(resp.tokens_in, resp.tokens_out),
        latency_ms=resp.latency_ms,
    )
    return {
        "final_answer": resp.content,
        "answered_by": TIER2_MODEL.display_name,
        "tier": 2,
        "usages": state["usages"] + [usage],
    }


async def finalize(state: RouterState) -> RouterState:
    spec = TIER1_MODELS[state["winner"]]
    return {
        "final_answer": state["draft_answer"],
        "answered_by": spec.display_name,
        "tier": 1,
    }


def _after_auction(state: RouterState) -> str:
    return "escalate" if state.get("escalated") else "draft"


def _after_draft(state: RouterState) -> str:
    return "escalate" if state.get("escalated") else "verify"


def _after_verify(state: RouterState) -> str:
    return "escalate" if state.get("escalated") else "finalize"


def build_graph():
    g = StateGraph(RouterState)
    g.add_node("bid_collection", bid_collection)
    g.add_node("auction", auction)
    g.add_node("draft", draft)
    g.add_node("verify", verify)
    g.add_node("escalate", escalate)
    g.add_node("finalize", finalize)

    g.set_entry_point("bid_collection")
    g.add_edge("bid_collection", "auction")
    g.add_conditional_edges("auction", _after_auction, {"escalate": "escalate", "draft": "draft"})
    g.add_conditional_edges("draft", _after_draft, {"escalate": "escalate", "verify": "verify"})
    g.add_conditional_edges("verify", _after_verify, {"escalate": "escalate", "finalize": "finalize"})
    g.add_edge("escalate", END)
    g.add_edge("finalize", END)
    return g.compile()


_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


async def run_query(query: str) -> RunResult:
    start = time.monotonic()
    state: RouterState = {"query": query, "usages": [], "escalated": False}
    final = await get_graph().ainvoke(state)

    usages = final.get("usages", [])
    total_cost = sum(u.cost_usd for u in usages)
    # Baseline: the same in/out volume sent straight to the frontier model
    answer_tokens_in = sum(u.tokens_in for u in usages if u.stage in ("draft", "escalate"))
    answer_tokens_out = sum(u.tokens_out for u in usages if u.stage in ("draft", "escalate"))
    baseline_cost = BASELINE_MODEL.estimate_cost(
        max(answer_tokens_in, 100), max(answer_tokens_out, 300))

    run = RunResult(
        id=uuid.uuid4().hex[:12],
        query=query,
        answer=final.get("final_answer", ""),
        answered_by=final.get("answered_by", "unknown"),
        tier=final.get("tier", 2),
        escalated=bool(final.get("escalated")),
        escalation_reason=final.get("escalation_reason"),
        bids=final.get("bids", []),
        winner=final.get("winner"),
        draft_answer=final.get("draft_answer"),
        verification=final.get("verification"),
        usages=usages,
        total_cost_usd=round(total_cost, 6),
        baseline_cost_usd=round(baseline_cost, 6),
        latency_ms=int((time.monotonic() - start) * 1000),
    )
    await get_store().save_run(run)
    return run
