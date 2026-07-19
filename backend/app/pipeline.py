"""The AuctionRouter LangGraph pipeline.

    bid_collection -> auction -> (escalate | draft) -> verify -> (escalate | finalize)

Bids are gathered in parallel from all tier-1 models. The auction node scores
them (0.7*confidence + 0.2*historical_accuracy - 0.1*cost) and either picks a
winner or escalates immediately on low confidence / high disagreement. The
verifier gates the draft; failures escalate to the frontier model.
"""

import asyncio
import logging
import re
import statistics
import time
import uuid
from typing import Optional, TypedDict

from langgraph.graph import END, StateGraph

from . import prompts
from .config import (BASELINE_MODEL, SPECULATIVE_HINT_MODELS, TIER1_MODELS,
                     TIER2_MODEL, VERIFIER_MODEL, settings)
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


# Confident bidders append their answer after this marker (see BID_SYSTEM),
# letting the pipeline skip the separate draft round-trip
_ANSWER_MARKER = "---ANSWER---"


def _split_bid_content(content: str) -> tuple[str, Optional[str]]:
    """Split a bid response into (json_part, speculative_answer)."""
    if _ANSWER_MARKER not in content:
        return content, None
    json_part, _, answer = content.partition(_ANSWER_MARKER)
    answer = answer.strip()
    return json_part, answer or None


async def _get_bid(model_key: str, query: str,
                   accuracy_task: "asyncio.Task[dict[str, float]]",
                   chat_history: list[dict]) -> tuple[Bid, Optional[Usage]]:
    spec = TIER1_MODELS[model_key]
    try:
        resp = await chat(spec, prompts.BID_SYSTEM,
                          prompts.bid_user(query, chat_history, spec.specialty),
                          timeout=settings.bid_timeout_s,
                          max_tokens=settings.max_bid_tokens,
                          prefer_paid=True)
        # The store read ran concurrently with the bid; by now it's done
        hist = (await accuracy_task).get(
            model_key, settings.default_historical_accuracy)
        json_part, speculative = _split_bid_content(resp.content)
        data = extract_json(json_part)
        confidence = _clamp(data.get("confidence", 0))
        # Ignore answers from bidders below the speculation bar — an answer
        # attached to a low bid means the model didn't follow the protocol
        if confidence < settings.speculative_draft_confidence:
            speculative = None
        bid = Bid(
            model_key=model_key,
            model_name=spec.display_name,
            confidence=confidence,
            estimated_difficulty=_clamp(data.get("estimated_difficulty", 0.5)),
            reason=str(data.get("reason", ""))[:300],
            historical_accuracy=hist,
            draft_answer=speculative,
        )
        usage = Usage(
            model_key=model_key, model_name=spec.display_name, stage="bid",
            tokens_in=resp.tokens_in, tokens_out=resp.tokens_out,
            cost_usd=spec.estimate_cost(resp.tokens_in, resp.tokens_out, resp.served_model),
            latency_ms=resp.latency_ms,
        )
        return bid, usage
    except (LLMError, ValueError, asyncio.TimeoutError, Exception) as e:
        try:
            hist = (await accuracy_task).get(
                model_key, settings.default_historical_accuracy)
        except Exception:
            hist = settings.default_historical_accuracy
        return Bid(model_key=model_key, model_name=spec.display_name,
                   confidence=0.0, reason="bid failed",
                   historical_accuracy=hist, error=str(e)[:200]), None


async def bid_collection(state: RouterState) -> RouterState:
    # Fired alongside the bids, not before them — with MongoDB this store
    # read is a network round-trip that shouldn't delay the bid launch
    accuracy_task = asyncio.ensure_future(get_store().historical_accuracy())
    tasks = {
        key: asyncio.ensure_future(
            _get_bid(key, state["query"], accuracy_task,
                     state.get("history", [])))
        for key in TIER1_MODELS
    }

    # Don't hold the auction for stragglers: once a confident bid lands,
    # the rest get bid_grace_s more, then they're cancelled and recorded
    # as timed-out bids.
    hard_deadline = time.monotonic() + settings.bid_timeout_s
    deadline = hard_deadline
    pending = set(tasks.values())
    while pending:
        timeout = deadline - time.monotonic()
        if timeout <= 0:
            break
        done, pending = await asyncio.wait(
            pending, timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
        confident = any(
            b.error is None and b.confidence >= settings.min_auction_confidence
            for b, _ in (t.result() for t in done))
        if confident:
            deadline = min(deadline,
                           time.monotonic() + settings.bid_grace_s)
    for t in pending:
        t.cancel()

    try:
        accuracy = await accuracy_task
    except Exception:
        accuracy = {}
    results = []
    for key, task in tasks.items():
        if task in pending:
            spec = TIER1_MODELS[key]
            hist = accuracy.get(key, settings.default_historical_accuracy)
            results.append((Bid(model_key=key, model_name=spec.display_name,
                                confidence=0.0, reason="bid timed out (soft)",
                                historical_accuracy=hist,
                                error="cancelled: soft bid timeout"), None))
        else:
            results.append(task.result())
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
    out: RouterState = {"winner": winner.model_key, "escalated": False}
    if winner.draft_answer:
        # The winning bid already carries an answer — skip the draft stage
        out["draft_answer"] = winner.draft_answer
    return out


async def draft(state: RouterState) -> RouterState:
    spec = TIER1_MODELS[state["winner"]]
    try:
        resp = await chat(spec, prompts.ANSWER_SYSTEM, state["query"],
                          history=state.get("history"), prefer_paid=True)
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
                          reasoning_effort=settings.verifier_reasoning_effort)
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


def _frontier_plan(state: RouterState) -> tuple[str, int]:
    """Pick GPT-5's (reasoning effort, max_tokens) from the bidders'
    difficulty estimates.

    Escalations of easy queries (a failed verification on something every
    bidder rated simple) don't deserve a minute of chain-of-thought or a
    frontier-sized token budget; hard queries get both.
    """
    hard = (settings.frontier_reasoning_effort, settings.max_frontier_tokens)
    difficulties = [b.estimated_difficulty for b in state.get("bids", [])
                    if b.error is None]
    if not difficulties:
        return hard
    mean_difficulty = sum(difficulties) / len(difficulties)
    if mean_difficulty >= settings.frontier_difficulty_threshold:
        return hard
    return (settings.frontier_easy_reasoning_effort,
            settings.max_frontier_tokens_easy)


async def escalate(state: RouterState) -> RouterState:
    effort, max_tokens = _frontier_plan(state)
    try:
        resp = await chat(TIER2_MODEL, prompts.FRONTIER_SYSTEM, state["query"],
                          max_tokens=max_tokens,
                          reasoning_effort=effort,
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
    if state.get("escalated"):
        return "escalate"
    # Winner's bid carried a speculative answer: verify it directly
    return "verify" if state.get("draft_answer") else "draft"


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
    g.add_conditional_edges("auction", _after_auction,
                            {"escalate": "escalate", "draft": "draft", "verify": "verify"})
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
    if final.get("tier") == 1 and not any(u.stage == "draft" for u in usages):
        # Speculative-draft path: the answer tokens live in the winner's bid
        winner_bids = [u for u in usages
                       if u.stage == "bid" and u.model_key == final.get("winner")]
        answer_tokens_in += sum(u.tokens_in for u in winner_bids)
        answer_tokens_out += sum(u.tokens_out for u in winner_bids)
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


# Fire-and-forget run persistence: the client shouldn't wait on a Mongo
# write it never reads. Strong refs keep tasks from being GC'd mid-flight.
_save_tasks: set[asyncio.Task] = set()


def _save_run_bg(run: RunResult) -> None:
    task = asyncio.ensure_future(get_store().save_run(run))
    _save_tasks.add(task)

    def _done(t: asyncio.Task) -> None:
        _save_tasks.discard(t)
        if not t.cancelled() and t.exception() is not None:
            logging.getLogger(__name__).warning(
                "save_run failed for %s: %s", run.id, t.exception())

    task.add_done_callback(_done)


def _trim_history(history: list[dict] | None) -> list[dict]:
    """Answer-level cap: most recent turns, per-turn char truncation.

    The per-turn budget is fixed (not divided by the actual turn count)
    so an old turn is truncated identically on every query — the stable
    message prefix is what lets provider-side prompt caching hit as the
    conversation grows.
    """
    turns = (history or [])[-settings.history_max_turns_answer:]
    per_turn = max(500, settings.history_max_chars_answer
                   // settings.history_max_turns_answer)
    return [{"role": t["role"], "content": t["content"][:per_turn]}
            for t in turns]


async def run_query(query: str, history: list[dict] | None = None) -> RunResult:
    start = time.monotonic()
    state: RouterState = {"query": query, "history": _trim_history(history),
                          "usages": [], "escalated": False}
    final = await get_graph().ainvoke(state)
    run = _make_run(query, final, start)
    _save_run_bg(run)
    return run


async def run_query_stream(query: str, history: list[dict] | None = None,
                           hint: str = "general"):
    """Streaming twin of the LangGraph pipeline.

    Reuses the same node functions but drives them imperatively so token
    deltas and stage transitions can be pushed to the client as they happen.
    Yields JSON-serializable event dicts; ends with {"type": "done", "run": ...}.
    """
    from .llm import chat_stream

    start = time.monotonic()
    state: dict = {"query": query, "history": _trim_history(history),
                   "usages": [], "escalated": False}

    # Hedge: the hint's model starts drafting at t=0, in parallel with the
    # bids. If the auction then picks it (the common case for a matching
    # hint), the draft is already in flight; otherwise the task is
    # cancelled for ~a tenth of a cent of wasted cheap-model tokens.
    hedge_key = SPECULATIVE_HINT_MODELS.get(hint, "gemini")
    hedge_spec = TIER1_MODELS[hedge_key]

    async def _hedge_draft():
        try:
            return await chat(hedge_spec, prompts.ANSWER_SYSTEM, query,
                              history=state["history"], prefer_paid=True)
        except Exception:
            return None

    hedge_task = asyncio.create_task(_hedge_draft())

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

    if (state.get("escalated") or state.get("winner") != hedge_key
            or state.get("draft_answer")):
        # Escalating, another model won, or the winning bid already
        # carried its own answer — the hedge isn't needed
        hedge_task.cancel()
    else:
        resp = await hedge_task
        if resp is not None and resp.content.strip():
            state["draft_answer"] = resp.content
            state["usages"] = state["usages"] + [Usage(
                model_key=hedge_spec.key, model_name=hedge_spec.display_name,
                stage="draft", tokens_in=resp.tokens_in,
                tokens_out=resp.tokens_out,
                cost_usd=hedge_spec.estimate_cost(resp.tokens_in,
                                                  resp.tokens_out,
                                                  resp.served_model),
                latency_ms=resp.latency_ms,
            )]
        # On hedge failure fall through: the normal draft stage runs

    if not state.get("escalated"):
        spec = TIER1_MODELS[state["winner"]]
        # Streaming-first: draft tokens go to the client as they exist, so
        # the user reads while the verifier judges. A failed verification
        # clears the provisional text via the existing "escalating" stage.
        if state.get("draft_answer"):
            # Winner's bid already carried the answer — verify it in
            # parallel while the client renders the draft
            yield {"type": "stage", "stage": "drafting",
                   "model": spec.display_name, "speculative": True}
            verify_task = asyncio.create_task(verify(state))
            yield {"type": "stage", "stage": "verifying"}
            # One event; the client's typewriter animation does the pacing
            yield {"type": "token", "text": state["draft_answer"]}
            state.update(await verify_task)
        else:
            yield {"type": "stage", "stage": "drafting", "model": spec.display_name}
            try:
                resp = None
                async for ev in chat_stream(spec, prompts.ANSWER_SYSTEM, query,
                                            history=state["history"],
                                            prefer_paid=True):
                    if ev["type"] == "delta":
                        yield {"type": "token", "text": ev["text"]}
                    elif ev["type"] == "final":
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

        if state.get("verification"):
            yield {
                "type": "verification",
                **state["verification"].model_dump(),
                "escalated": state.get("escalated", False),
                "reason": state.get("escalation_reason"),
            }
        if state.get("draft_answer") and not state.get("escalated"):
            # Verified: flip the client's provisional badge; tokens were
            # already streamed live
            yield {"type": "stage", "stage": "delivering",
                   "model": spec.display_name}

    if state.get("escalated"):
        effort, max_tokens = _frontier_plan(state)
        yield {"type": "stage", "stage": "escalating",
               "model": TIER2_MODEL.display_name,
               "reason": state.get("escalation_reason"),
               "effort": effort}
        try:
            resp = None
            async for ev in chat_stream(TIER2_MODEL, prompts.FRONTIER_SYSTEM, query,
                                        max_tokens=max_tokens,
                                        reasoning_effort=effort,
                                        history=state["history"]):
                if ev["type"] == "delta":
                    yield {"type": "token", "text": ev["text"]}
                elif ev["type"] == "reasoning_delta":
                    yield {"type": "reasoning", "text": ev["text"]}
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
    _save_run_bg(run)
    yield {"type": "done", "run": run.model_dump(mode="json")}
