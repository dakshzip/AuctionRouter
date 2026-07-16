"""The AuctionRouter LangGraph pipeline.

    bid_collection -> auction -> (escalate | draft) -> verify -> (escalate | finalize)

Bids are gathered in parallel from all tier-1 models. The auction node scores
them (0.7*confidence + 0.2*historical_accuracy - 0.1*cost) and either picks a
winner or escalates immediately on low confidence / high disagreement. The
verifier gates the draft; failures escalate to the frontier model.
"""

import asyncio
import re
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
    history: list[dict]
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


async def _get_bid(model_key: str, query: str, accuracy: dict[str, float],
                   chat_history: list[dict]) -> tuple[Bid, Optional[Usage]]:
    spec = TIER1_MODELS[model_key]
    hist = accuracy.get(model_key, settings.default_historical_accuracy)
    try:
        resp = await chat(spec, prompts.BID_SYSTEM,
                          prompts.bid_user(query, chat_history, spec.specialty),
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
            cost_usd=spec.estimate_cost(resp.tokens_in, resp.tokens_out, resp.served_model),
            latency_ms=resp.latency_ms,
        )
        return bid, usage
    except (LLMError, ValueError, asyncio.TimeoutError, Exception) as e:
        return Bid(model_key=model_key, model_name=spec.display_name,
                   confidence=0.0, reason="bid failed",
                   historical_accuracy=hist, error=str(e)[:200]), None


async def bid_collection(state: RouterState) -> RouterState:
    accuracy = await get_store().historical_accuracy()
    results = await asyncio.gather(
        *(_get_bid(key, state["query"], accuracy, state.get("history", []))
          for key in TIER1_MODELS)
    )
    bids = [b for b, _ in results]
    usages = [u for _, u in results if u is not None]

    # Normalize per-model output cost to 0..1 for the auction's cost term.
    # Free-primary models are discounted: they only cost their fallback
    # price when the free pool is congested (~30% of the time).
    costs = {
        k: m.cost_per_mtok_out * (0.3 if m.openrouter_id.endswith(":free") else 1.0)
        for k, m in TIER1_MODELS.items()
    }
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

    # Disagreement only matters when nobody is sure: with specialist
    # bidders, a wide spread (coder bids 0.3 on a trivia question) is the
    # system working, not a red flag — so skip the check when a model is
    # highly confident.
    if len(confidences) >= 2 and max_conf < settings.disagreement_exempt_confidence:
        spread = statistics.pstdev(confidences)
        if spread > settings.disagreement_stddev:
            return {"escalated": True,
                    "escalation_reason": f"Strong model disagreement (stddev {spread:.2f} > {settings.disagreement_stddev})"}

    winner = max(valid, key=lambda b: b.auction_score)
    return {"winner": winner.model_key, "escalated": False}


async def draft(state: RouterState) -> RouterState:
    spec = TIER1_MODELS[state["winner"]]
    try:
        resp = await chat(spec, prompts.ANSWER_SYSTEM, state["query"],
                          history=state.get("history"))
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


# Leaked chain-of-thought in a "final" answer means the model was struggling;
# the verifier should never pass it even if the end value happens to be right.
_THINKING_ARTIFACTS = re.compile(
    r"(?im)^\s*(wait|hmm+|hold on)\b"
    r"|\b(wait,? (?:no|but|that)|hmm+,|let me (?:recalculate|recheck|reconsider|try again|start over)"
    r"|actually,? (?:no|wait|that'?s (?:wrong|not right))|scratch that|i made an? (?:error|mistake))\b"
)


async def verify(state: RouterState) -> RouterState:
    try:
        resp = await chat(VERIFIER_MODEL, prompts.VERIFY_SYSTEM,
                          prompts.verify_user(state["query"], state["draft_answer"],
                                              state.get("history")),
                          reasoning_effort="medium")
        data = extract_json(resp.content)
        score = _clamp(data.get("score", 0))
        # Enforce score = min(subscores) server-side; models sometimes
        # report an optimistic overall despite a low dimension
        subscores = [_clamp(data[k]) for k in
                     ("correctness", "completeness", "commitment", "presentation")
                     if k in data]
        if subscores:
            score = min(score, *subscores)
        verification = Verification(
            score=score,
            # our (possibly stricter) score overrides the model's own verdict
            passed=score >= settings.verification_threshold
            and bool(data.get("pass", True)),
            feedback=str(data.get("feedback", ""))[:500],
        )
    except (LLMError, ValueError) as e:
        # If the verifier itself breaks, fail safe: escalate
        verification = Verification(score=0.0, passed=False,
                                    feedback=f"Verifier error: {str(e)[:150]}")
        resp = None

    # Deterministic guard: cap the score when the draft contains
    # thinking-out-loud artifacts, independent of the verifier's judgment
    artifacts = _THINKING_ARTIFACTS.findall(state["draft_answer"] or "")
    if artifacts and verification.score > 0.5:
        verification = Verification(
            score=0.5,
            passed=False,
            feedback="Draft contains unresolved reasoning artifacts "
                     "(thinking out loud / self-corrections). "
                     + verification.feedback,
        )

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
        resp = await chat(TIER2_MODEL, prompts.FRONTIER_SYSTEM, state["query"],
                          max_tokens=settings.max_frontier_tokens,
                          reasoning_effort=settings.frontier_reasoning_effort,
                          history=state.get("history"))
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


def _make_run(query: str, final: dict, start: float) -> RunResult:
    usages = final.get("usages", [])
    total_cost = sum(u.cost_usd for u in usages)
    # Baseline: the same in/out volume sent straight to the frontier model
    answer_tokens_in = sum(u.tokens_in for u in usages if u.stage in ("draft", "escalate"))
    answer_tokens_out = sum(u.tokens_out for u in usages if u.stage in ("draft", "escalate"))
    baseline_cost = BASELINE_MODEL.estimate_cost(
        max(answer_tokens_in, 100), max(answer_tokens_out, 300))

    return RunResult(
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


def _trim_history(history: list[dict] | None) -> list[dict]:
    """Answer-level cap: most recent turns, per-turn char truncation."""
    turns = (history or [])[-settings.history_max_turns_answer:]
    per_turn = settings.history_max_chars_answer // max(len(turns), 1)
    return [{"role": t["role"], "content": t["content"][:max(per_turn, 500)]}
            for t in turns]


async def run_query(query: str, history: list[dict] | None = None) -> RunResult:
    start = time.monotonic()
    state: RouterState = {"query": query, "history": _trim_history(history),
                          "usages": [], "escalated": False}
    final = await get_graph().ainvoke(state)
    run = _make_run(query, final, start)
    await get_store().save_run(run)
    return run


async def run_query_stream(query: str, history: list[dict] | None = None):
    """Streaming twin of the LangGraph pipeline.

    Reuses the same node functions but drives them imperatively so token
    deltas and stage transitions can be pushed to the client as they happen.
    Yields JSON-serializable event dicts; ends with {"type": "done", "run": ...}.
    """
    from .llm import chat_stream

    start = time.monotonic()
    state: dict = {"query": query, "history": _trim_history(history),
                   "usages": [], "escalated": False}

    yield {"type": "stage", "stage": "bidding"}
    state.update(await bid_collection(state))
    state.update(await auction(state))
    yield {
        "type": "auction",
        "bids": [b.model_dump() for b in state["bids"]],
        "winner": state.get("winner"),
        "escalated": state.get("escalated", False),
        "reason": state.get("escalation_reason"),
    }

    if not state.get("escalated"):
        spec = TIER1_MODELS[state["winner"]]
        yield {"type": "stage", "stage": "drafting", "model": spec.display_name}
        try:
            # Draft tokens are NOT forwarded to the client: the draft isn't
            # final until verification passes, and streaming text that later
            # gets replaced by the frontier answer is a confusing UX.
            resp = None
            async for ev in chat_stream(spec, prompts.ANSWER_SYSTEM, query,
                                        history=state["history"]):
                if ev["type"] == "final":
                    resp = ev["response"]
            if resp is None or not resp.content.strip():
                state["escalated"] = True
                state["escalation_reason"] = f"{spec.display_name} returned an empty draft"
            else:
                state["draft_answer"] = resp.content
                state["usages"] = state["usages"] + [Usage(
                    model_key=spec.key, model_name=spec.display_name, stage="draft",
                    tokens_in=resp.tokens_in, tokens_out=resp.tokens_out,
                    cost_usd=spec.estimate_cost(resp.tokens_in, resp.tokens_out,
                                                resp.served_model),
                    latency_ms=resp.latency_ms,
                )]
        except LLMError as e:
            state["escalated"] = True
            state["escalation_reason"] = f"Winner failed to answer: {str(e)[:150]}"

        if state.get("draft_answer"):
            yield {"type": "stage", "stage": "verifying"}
            state.update(await verify(state))
            yield {
                "type": "verification",
                **state["verification"].model_dump(),
                "escalated": state.get("escalated", False),
                "reason": state.get("escalation_reason"),
            }
            if not state.get("escalated"):
                # Draft is now verified-final: stream it to the client in
                # chunks (it was generated silently during the draft stage)
                yield {"type": "stage", "stage": "delivering",
                       "model": spec.display_name}
                text = state["draft_answer"]
                step = 80
                for i in range(0, len(text), step):
                    yield {"type": "token", "text": text[i:i + step]}
                    await asyncio.sleep(0.02)

    if state.get("escalated"):
        yield {"type": "stage", "stage": "escalating",
               "model": TIER2_MODEL.display_name,
               "reason": state.get("escalation_reason")}
        try:
            resp = None
            async for ev in chat_stream(TIER2_MODEL, prompts.FRONTIER_SYSTEM, query,
                                        max_tokens=settings.max_frontier_tokens,
                                        reasoning_effort=settings.frontier_reasoning_effort,
                                        history=state["history"]):
                if ev["type"] == "delta":
                    yield {"type": "token", "text": ev["text"]}
                else:
                    resp = ev["response"]
            if resp is None or not resp.content.strip():
                raise LLMError(f"{TIER2_MODEL.openrouter_id}: empty response")
            state["final_answer"] = resp.content
            state["answered_by"] = TIER2_MODEL.display_name
            state["tier"] = 2
            state["usages"] = state["usages"] + [Usage(
                model_key=TIER2_MODEL.key, model_name=TIER2_MODEL.display_name,
                stage="escalate", tokens_in=resp.tokens_in, tokens_out=resp.tokens_out,
                cost_usd=TIER2_MODEL.estimate_cost(resp.tokens_in, resp.tokens_out,
                                                   resp.served_model),
                latency_ms=resp.latency_ms,
            )]
        except LLMError as e:
            if state.get("draft_answer"):
                spec = TIER1_MODELS[state["winner"]]
                state["final_answer"] = state["draft_answer"]
                state["answered_by"] = f"{spec.display_name} (frontier unavailable)"
                state["tier"] = 1
                state["escalation_reason"] = (state.get("escalation_reason") or "") \
                    + f" | frontier failed: {str(e)[:150]}"
                yield {"type": "frontier_failed", "reason": str(e)[:200]}
            else:
                yield {"type": "error", "message": str(e)[:300]}
                return
    else:
        state.update(await finalize(state))

    run = _make_run(query, state, start)
    await get_store().save_run(run)
    yield {"type": "done", "run": run.model_dump(mode="json")}
