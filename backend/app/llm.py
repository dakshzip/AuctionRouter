"""Thin async OpenRouter client with JSON-mode helpers."""

import asyncio
import json
import re
import time
from typing import Any, AsyncIterator

from urllib.parse import urlparse

import httpx

from .config import ModelSpec, settings


# imported by: pipeline.py, webgate.py
class LLMError(Exception):
    pass


def _citation_items(annotations: list | None) -> list[dict]:
    """Pull {url, title} out of OpenRouter's url_citation annotations."""
    out: list[dict] = []
    seen: set[str] = set()
    for a in annotations or []:
        if not isinstance(a, dict):
            continue
        cite = a.get("url_citation") or {}
        url = cite.get("url") or ""
        if not url.startswith("http") or url in seen:
            continue
        seen.add(url)
        out.append({"url": url, "title": str(cite.get("title") or "")[:160]})
    return out


# imported by: tests/test_citations.py
def _citation_urls(annotations: list | None) -> list[str]:
    return [c["url"] for c in _citation_items(annotations)]


def _new_citations(choice: dict, seen: list[dict]) -> list[dict]:
    """Citations in this chunk that `seen` doesn't already have.

    A streamed choice can carry annotations on the delta or on the final
    message, and the same URL often arrives in both.
    """
    known = {c["url"] for c in seen}
    out: list[dict] = []
    for src in (choice.get("delta") or {}, choice.get("message") or {}):
        for c in _citation_items(src.get("annotations")):
            if c["url"] not in known:
                known.add(c["url"])
                out.append(c)
    return out


def _retry_delay(resp: httpx.Response) -> float:
    """Seconds to wait before retrying a 429, capped.

    The cap is the point: a provider asking for 60s would blow the request
    timeout on a call a user is waiting on. Retry-After also has an HTTP-date
    form, which float() can't read and which isn't worth parsing under a cap
    this small.
    """
    try:
        return min(float(resp.headers.get("Retry-After", 2.0)), 2.0)
    except ValueError:
        return 2.0


# The web plugin writes citations as a bare domain in fullwidth brackets —
# 【pmindia.gov.in】 — which renders as text that looks like a link but isn't.
# The real URLs come back in message.annotations, so the two can be matched up.
_CITE_MARKER = re.compile(r"【\s*([^【】\s]+?)\s*】")


# imported by: tests/test_citations.py
def link_citations(text: str, citations: list) -> str:
    """Turn 【domain】 markers into real markdown links.

    Matches each marker to the annotation whose host it belongs to, so the
    link lands on the actual cited page rather than the site's front door.
    Markers with no matching annotation are left exactly as they are — a
    plain-domain link would be a guess, and a wrong link is worse than none.

    The annotation title rides along as the link's markdown title, which is
    what the frontend's hover preview reads. Accepts either {url, title}
    dicts or bare URL strings.
    """
    if not text or not citations:
        return text
    hosts = []
    for c in citations:
        item = {"url": c, "title": ""} if isinstance(c, str) else c
        try:
            host = urlparse(item["url"]).netloc.lower()
        except (ValueError, KeyError, TypeError):
            continue
        hosts.append((host.removeprefix("www."), item))

    def repl(m: re.Match) -> str:
        label = m.group(1)
        # removeprefix, not lstrip: lstrip strips any of "w"/"." from the
        # front, turning "wikipedia.org" into "ikipedia.org".
        key = label.lower().removeprefix("www.")
        matches = [item for host, item in hosts
                   if host == key or host.endswith("." + key)
                   or key.endswith(host)]
        if not matches:
            return m.group(0)
        # Several citations can share a host; prefer one that carries a title,
        # since that's what the hover preview has to show.
        item = next((i for i in matches if i.get("title")), matches[0])
        title = (item.get("title") or "").replace('"', "'")
        suffix = f' "{title}"' if title else ""
        # The model glues the marker straight onto the preceding word
        # ("Self-Defence Forcesen.wikipedia.org"), so give the link room
        # unless it already follows whitespace or an opening bracket.
        start = m.start()
        lead = "" if start == 0 or text[start - 1] in " \t\n([" else " "
        return f"{lead}[{label}]({item['url']}{suffix})"

    return _CITE_MARKER.sub(repl, text)


async def _iter_stream_payloads(resp: httpx.Response) -> AsyncIterator[dict]:
    """Decoded SSE payloads, with keep-alives, [DONE] and junk chunks absorbed.

    Split out so the consuming loop reads as "for each chunk of the answer"
    rather than as line-protocol handling.
    """
    async for line in resp.aiter_lines():
        if not line.startswith("data: "):
            continue
        payload = line[len("data: "):].strip()
        if payload == "[DONE]":
            return
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            continue
        yield data


async def _open_stream(model: ModelSpec, body: dict,
                       timeout: float) -> AsyncIterator[dict]:
    """Connect, retry transient 429s, and yield decoded payloads.

    Owns the connection so chat_stream doesn't have to: everything here is
    retry and transport, nothing is about the answer being assembled.
    """
    attempts = 3
    for attempt in range(attempts):
        try:
            async with get_client().stream(
                "POST", "/chat/completions", json=body, timeout=timeout) as resp:
                if resp.status_code == 429 and attempt < attempts - 1:
                    await asyncio.sleep(_retry_delay(resp))
                    continue
                if resp.status_code != 200:
                    text = (await resp.aread()).decode(errors="replace")
                    raise LLMError(
                        f"{model.openrouter_id}: HTTP {resp.status_code}: {text[:300]}")
                async for data in _iter_stream_payloads(resp):
                    yield data
            return
        except httpx.HTTPError as e:
            raise LLMError(
                f"{model.openrouter_id}: {type(e).__name__}: {e}") from e


class LLMResponse:
    def __init__(self, content: str, tokens_in: int, tokens_out: int,
                 latency_ms: int, served_model: str = ""):
        self.content = content
        self.tokens_in = tokens_in
        self.tokens_out = tokens_out
        self.latency_ms = latency_ms
        self.served_model = served_model  # which model actually answered


_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            base_url=settings.openrouter_base_url,
            headers={
                "Authorization": f"Bearer {settings.openrouter_api_key}",
                "HTTP-Referer": "https://github.com/auctionrouter",
                "X-Title": "AuctionRouter",
            },
            timeout=settings.request_timeout_s,
        )
    return _client


# imported by: main.py, evals/run_evals.py
async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def _build_messages(system: str, user: str,history: list[dict] | None) -> list[dict]:
    # Ground every model in the current date so it doesn't treat recent
    # events as "hasn't happened yet" (and flags needs_web correctly)
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return [
        {"role": "system", "content": f"Today's date is {today}.\n\n{system}"},
        *({"role": t["role"], "content": t["content"]} for t in (history or [])),
        {"role": "user", "content": user}
    ]


def _request_body(model: ModelSpec, system: str, user: str,
                  max_tokens: int | None,
                  reasoning_effort: str | None,
                  history: list[dict] | None,
                  prefer_paid: bool,
                  web: bool = False) -> dict:
    # Latency-critical calls (bids, drafts) skip the free pool: paid
    # endpoints respond in a fraction of the time
    model_id = model.fallback_id if prefer_paid and model.fallback_id else model.openrouter_id
    body: dict = {
        "model": model_id,
        "messages": _build_messages(system, user, history),
        "max_tokens": max_tokens or settings.max_answer_tokens,
    }
    if reasoning_effort:
        body["reasoning"] = {"effort": reasoning_effort}
    if model.fallback_id and not prefer_paid:
        # OpenRouter fallback routing: try free primary, then paid fallback
        body["models"] = [model.openrouter_id, model.fallback_id]
    if settings.openrouter_provider_sort:
        # Route to the fastest provider for the model rather than the
        # default (cheapest) — big variance cut for multi-provider models
        body["provider"] = {"sort": settings.openrouter_provider_sort}
    if web and settings.web_search_enabled:
        # OpenRouter web plugin: runs a search and injects results into
        # context before the model answers ($0.004/search)
        body["plugins"] = [{"id": "web",
                            "max_results": settings.web_search_max_results}]
    return body


# imported by: pipeline.py, webgate.py, evals/run_evals.py
async def chat(model: ModelSpec, system: str, user: str,
               timeout: float | None = None,
               max_tokens: int | None = None,
               reasoning_effort: str | None = None,
               history: list[dict] | None = None,
               prefer_paid: bool = False,
               web: bool = False) -> LLMResponse:
    start = time.monotonic()
    body = _request_body(model, system, user, max_tokens,
                         reasoning_effort, history, prefer_paid, web)

    # Free-tier models often 429 transiently ("rate-limited upstream,
    # retry shortly"), so retry a couple of times honoring Retry-After.
    attempts = 3
    resp: httpx.Response | None = None
    try:
        for attempt in range(attempts):
            resp = await get_client().post(
                "/chat/completions",
                json=body,
                timeout=timeout or settings.request_timeout_s,
            )
            if resp.status_code != 429 or attempt == attempts - 1:
                break
            await asyncio.sleep(_retry_delay(resp))
    except httpx.HTTPError as e:
        # Transport faults become LLMError so every caller can catch that one
        # type and let anything else through as the bug it is.
        raise LLMError(f"{model.openrouter_id}: {type(e).__name__}: {e}") from e
    if resp is None:
        raise LLMError(f"{model.openrouter_id}: no request was made")

    latency_ms = int((time.monotonic() - start) * 1000)
    if resp.status_code != 200:
        raise LLMError(f"{model.openrouter_id}: HTTP {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    if "error" in data:  # OpenRouter can embed provider errors in a 200
        raise LLMError(f"{model.openrouter_id}: {str(data['error'])[:300]}")
    try:
        message = data["choices"][0]["message"]
        content = message["content"] or ""
    except (KeyError, IndexError) as e:
        raise LLMError(f"{model.openrouter_id}: malformed response: {e}")
    content = link_citations(content, _citation_items(message.get("annotations")))
    usage = data.get("usage") or {}
    return LLMResponse(
        content=content,
        tokens_in=usage.get("prompt_tokens", 0),
        tokens_out=usage.get("completion_tokens", 0),
        latency_ms=latency_ms,
        served_model=data.get("model", model.openrouter_id),
    )


# imported by: pipeline.py (lazy import in run_query_stream)
async def chat_stream(model: ModelSpec, system: str, user: str,
                      timeout: float | None = None,
                      max_tokens: int | None = None,
                      reasoning_effort: str | None = None,
                      history: list[dict] | None = None,
                      prefer_paid: bool = False,
                      web: bool = False):
    """Streaming variant of chat().

    Yields {"type": "delta", "text": ...} per token chunk, then a final
    {"type": "final", "response": LLMResponse} with full content and usage.
    """
    body = _request_body(model, system, user, max_tokens,
                         reasoning_effort, history, prefer_paid, web)
    body["stream"] = True
    body["stream_options"] = {"include_usage": True}

    start = time.monotonic()
    parts: list[str] = []
    citations: list[dict] = []
    tokens_in = tokens_out = 0
    served = model.openrouter_id

    async for data in _open_stream(model, body,
                                   timeout or settings.request_timeout_s):
        if "error" in data:
            raise LLMError(f"{model.openrouter_id}: {str(data['error'])[:300]}")
        served = data.get("model", served)
        usage = data.get("usage")
        if usage:
            tokens_in = usage.get("prompt_tokens", tokens_in)
            tokens_out = usage.get("completion_tokens", tokens_out)
        choices = data.get("choices") or []
        if not choices:
            continue
        # Collected as they stream so the finished answer can be rewritten
        # with real links below.
        citations += _new_citations(choices[0], citations)
        delta = choices[0].get("delta") or {}
        thinking = delta.get("reasoning") or ""
        if thinking:
            # Reasoning summaries stream before content on reasoning
            # models; provider support varies
            yield {"type": "reasoning_delta", "text": thinking}
        piece = delta.get("content") or ""
        if piece:
            parts.append(piece)
            yield {"type": "delta", "text": piece}

    yield {
        "type": "final",
        "response": LLMResponse(
            # Deltas streamed raw; the finished answer gets real links. The
            # client replaces the streamed text with this on `done`.
            content=link_citations("".join(parts), citations),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=int((time.monotonic() - start) * 1000),
            served_model=served,
        ),
    }


# imported by: pipeline.py, evals/run_evals.py
def extract_json(text: str) -> dict[str, Any]:
    """Pull the first JSON object out of a model response.

    Handles raw JSON, ```json fences, and JSON embedded in prose.
    """
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    else:
        brace = re.search(r"\{.*\}", text, re.DOTALL)
        if brace:
            text = brace.group(0)
    return json.loads(text)
