"""Thin async OpenRouter client with JSON-mode helpers."""

import asyncio
import json
import re
import time
from typing import Any

import httpx

from .config import ModelSpec, settings


class LLMError(Exception):
    pass


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


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def _build_messages(system: str, user: str,
                    history: list[dict] | None) -> list[dict]:
    return [
        {"role": "system", "content": system},
        *({"role": t["role"], "content": t["content"]} for t in (history or [])),
        {"role": "user", "content": user},
    ]


async def chat(model: ModelSpec, system: str, user: str,
               timeout: float | None = None,
               max_tokens: int | None = None,
               reasoning_effort: str | None = None,
               history: list[dict] | None = None) -> LLMResponse:
    start = time.monotonic()
    body: dict = {
        "model": model.openrouter_id,
        "messages": _build_messages(system, user, history),
        "max_tokens": max_tokens or settings.max_answer_tokens,
    }
    if reasoning_effort:
        body["reasoning"] = {"effort": reasoning_effort}
    if model.fallback_id:
        # OpenRouter fallback routing: try free primary, then paid fallback
        body["models"] = [model.openrouter_id, model.fallback_id]

    # Free-tier models often 429 transiently ("rate-limited upstream,
    # retry shortly"), so retry a couple of times honoring Retry-After.
    attempts = 3
    for attempt in range(attempts):
        resp = await get_client().post(
            "/chat/completions",
            json=body,
            timeout=timeout or settings.request_timeout_s,
        )
        if resp.status_code != 429 or attempt == attempts - 1:
            break
        retry_after = min(float(resp.headers.get("Retry-After", 2)), 2.0)
        await asyncio.sleep(retry_after)

    latency_ms = int((time.monotonic() - start) * 1000)
    if resp.status_code != 200:
        raise LLMError(f"{model.openrouter_id}: HTTP {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    if "error" in data:  # OpenRouter can embed provider errors in a 200
        raise LLMError(f"{model.openrouter_id}: {str(data['error'])[:300]}")
    try:
        content = data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError) as e:
        raise LLMError(f"{model.openrouter_id}: malformed response: {e}")
    usage = data.get("usage") or {}
    return LLMResponse(
        content=content,
        tokens_in=usage.get("prompt_tokens", 0),
        tokens_out=usage.get("completion_tokens", 0),
        latency_ms=latency_ms,
        served_model=data.get("model", model.openrouter_id),
    )


async def chat_stream(model: ModelSpec, system: str, user: str,
                      timeout: float | None = None,
                      max_tokens: int | None = None,
                      reasoning_effort: str | None = None,
                      history: list[dict] | None = None):
    """Streaming variant of chat().

    Yields {"type": "delta", "text": ...} per token chunk, then a final
    {"type": "final", "response": LLMResponse} with full content and usage.
    """
    body: dict = {
        "model": model.openrouter_id,
        "messages": _build_messages(system, user, history),
        "max_tokens": max_tokens or settings.max_answer_tokens,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if reasoning_effort:
        body["reasoning"] = {"effort": reasoning_effort}
    if model.fallback_id:
        body["models"] = [model.openrouter_id, model.fallback_id]

    start = time.monotonic()
    parts: list[str] = []
    tokens_in = tokens_out = 0
    served = model.openrouter_id

    attempts = 3
    for attempt in range(attempts):
        async with get_client().stream(
            "POST", "/chat/completions", json=body,
            timeout=timeout or settings.request_timeout_s,
        ) as resp:
            if resp.status_code == 429 and attempt < attempts - 1:
                retry_after = min(float(resp.headers.get("Retry-After", 2)), 2.0)
                await asyncio.sleep(retry_after)
                continue
            if resp.status_code != 200:
                text = (await resp.aread()).decode(errors="replace")
                raise LLMError(f"{model.openrouter_id}: HTTP {resp.status_code}: {text[:300]}")
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                payload = line[len("data: "):].strip()
                if payload == "[DONE]":
                    break
                try:
                    data = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                if "error" in data:
                    raise LLMError(f"{model.openrouter_id}: {str(data['error'])[:300]}")
                served = data.get("model", served)
                usage = data.get("usage")
                if usage:
                    tokens_in = usage.get("prompt_tokens", tokens_in)
                    tokens_out = usage.get("completion_tokens", tokens_out)
                choices = data.get("choices") or []
                if choices:
                    piece = (choices[0].get("delta") or {}).get("content") or ""
                    if piece:
                        parts.append(piece)
                        yield {"type": "delta", "text": piece}
        break

    yield {
        "type": "final",
        "response": LLMResponse(
            content="".join(parts),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=int((time.monotonic() - start) * 1000),
            served_model=served,
        ),
    }


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
