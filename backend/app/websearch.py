"""Tavily image search — the only search call this backend makes itself.

Text web search is delegated to OpenRouter's `web` plugin (see llm.py), which
runs server-side and returns no images. So when a bidder flags a query as
image-worthy (Bid.wants_images) we run one small Tavily search of our own just
to harvest 2-3 pictures.

Best-effort by design: every failure path returns an empty list. An answer must
never be delayed or degraded because the image lookup fell over.
"""

import logging
import re

import httpx

from .config import settings
from .schemas import SourceImage

log = logging.getLogger(__name__)

TAVILY_URL = "https://api.tavily.com/search"

_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=settings.image_search_timeout_s)
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def enabled() -> bool:
    return bool(settings.image_search_enabled and settings.tavily_api_key)


# Whether the key actually WORKS, as opposed to merely being set. /health used
# to report image_search:true for any non-empty key, which is how a deployment
# with an unusable key looked healthy while silently returning no images on
# every query. Updated by each real search; seeded by verify() at startup.
_status: dict = {"state": "unknown", "detail": "no search attempted yet"}


def status() -> dict:
    """Real state of the image search: disabled | ok | error | unknown."""
    if not enabled():
        why = ("image_search_enabled=false" if settings.tavily_api_key
               else "TAVILY_API_KEY not set")
        return {"state": "disabled", "detail": why}
    return dict(_status)


def _record(state: str, detail: str) -> None:
    _status.update(state=state, detail=detail[:200])


async def verify() -> None:
    """One real search at startup, so a bad key fails loudly at deploy time.

    Costs a single Tavily credit per process start. Worth it: the alternative
    is discovering the key is wrong only when a user notices missing images,
    which is exactly what happened in production.
    """
    if not enabled():
        return
    images = await _search_once("test query", 1)
    if images:
        _record("ok", "startup probe returned images")


# An image search matches on the literal words it is given, so the phrasing a
# user wraps their subject in ("show me photos of…", "what does … look like")
# becomes noise: it pulls back stock art of the words themselves instead of
# the thing being asked about. Strip the scaffolding, keep the subject.
_LEAD = re.compile(r"""(?ix)^\s*
    (?: (?:can\s+you\s+|could\s+you\s+|please\s+)*
        (?:show\s+me|show|find\s+me|find|get\s+me|give\s+me|
           i\s+want\s+to\s+see|i\s+wanna\s+see|let\s+me\s+see)
        \s+ (?:some\s+|a\s+few\s+|the\s+)?
        (?:photos?|pictures?|pics?|images?)? \s* (?:of\s+)?
      | (?:what|how)\s+(?:does|do|did)\s+
      | (?:photos?|pictures?|pics?|images?)\s+of\s+
    )""")

_TAIL = re.compile(r"(?i)\s*\blooks?\s+like\b\s*[?.!]*\s*$")


def search_subject(query: str) -> str:
    """Reduce a conversational query to the thing to search images for."""
    subject = _TAIL.sub("", _LEAD.sub("", query)).strip(" ?.!,")
    # A near-empty result means the query was all scaffolding and no subject
    # (or the patterns overreached) — the original is the safer search.
    return subject if len(subject) >= 3 else query.strip()


# Markdown the answer may open with, stripped so it doesn't reach the search
_MD = re.compile(r"[*_`#>\[\]]|\\\(|\\\)|\$\$?")


def image_query(query: str, answer: str | None = None) -> str:
    """What to actually search for images of.

    The question is the wrong thing to search: "who won the world cup" returns
    the most famous winner, not the one this answer names. The answer's opening
    sentence carries the entity the user is actually being told about, so it
    makes a far better image query — "Spain won the 2026 FIFA World Cup" finds
    Spain, where the bare question finds Argentina.
    """
    subject = search_subject(query)
    if not answer:
        return subject
    # First sentence of the first real paragraph, de-marked-down
    body = _MD.sub("", answer).strip()
    first = ""
    for line in body.splitlines():
        line = line.strip()
        if line:
            first = line
            break
    for stop in (". ", "! ", "? "):
        idx = first.find(stop)
        if idx > 0:
            first = first[:idx]
            break
    first = first.strip(" .!?,:;")[:120]
    # Too short to identify anything on its own — keep the question's subject
    if len(first) < 15:
        return subject
    return first


def _parse(data: dict, limit: int) -> list[SourceImage]:
    """Map Tavily's `images` array to SourceImages, dropping junk.

    With include_image_descriptions the entries are dicts; without it they
    are bare URL strings. Handle both so the flag can be flipped freely.
    """
    out: list[SourceImage] = []
    seen: set[str] = set()
    for item in data.get("images") or []:
        if isinstance(item, str):
            url, desc = item, ""
        elif isinstance(item, dict):
            url, desc = item.get("url") or "", item.get("description") or ""
        else:
            continue
        url = url.strip()
        # https only: the deployed Space is served over TLS, so a plain-http
        # thumbnail is blocked as mixed content and renders as a dead box.
        if not url.startswith("https://") or url in seen:
            continue
        seen.add(url)
        out.append(SourceImage(url=url, description=str(desc)[:200]))
        if len(out) >= limit:
            break
    return out


async def search_images(query: str, limit: int | None = None,
                        answer: str | None = None) -> list[SourceImage]:
    """Fetch up to `limit` images. Never raises.

    Pass `answer` whenever it exists: images are only as relevant as the text
    they are searched with, and the answer names the entity the question only
    gestures at.
    """
    limit = limit or settings.image_search_max
    if not enabled() or not query.strip() or limit < 1:
        return []
    # Answer-derived first (accurate), question-derived second (reliable). A
    # long specific sentence sometimes matches nothing at all, which showed up
    # as the strip silently vanishing on queries that had images a moment ago.
    attempts = [image_query(query, answer)]
    fallback = search_subject(query)
    if fallback and fallback != attempts[0]:
        attempts.append(fallback)
    for attempt in attempts:
        images = await _search_once(attempt, limit)
        if images:
            return images
    return []


async def _search_once(subject: str, limit: int) -> list[SourceImage]:
    try:
        resp = await get_client().post(
            TAVILY_URL,
            headers={"Authorization": f"Bearer {settings.tavily_api_key}"},
            json={
                "query": subject,
                "include_images": True,
                "include_image_descriptions": True,
                # Images come from the same crawl as the text results, so a
                # basic search is enough — advanced costs 2 credits.
                "search_depth": "basic",
                "max_results": settings.web_search_max_results,
            },
        )
        if resp.status_code != 200:
            detail = f"HTTP {resp.status_code}: {resp.text[:120]}"
            log.warning("tavily: %s", detail)
            # 401/403 mean the key itself is bad — the case /health must not
            # keep calling healthy.
            _record("error", detail)
            return []
        images = _parse(resp.json(), limit)
        _record("ok", f"last search returned {len(images)} image(s)")
        return images
    except Exception as e:  # network, timeout, malformed JSON — all non-fatal
        # Type included: timeout exceptions stringify to "" and are otherwise
        # indistinguishable from a genuine failure in the log.
        detail = f"{type(e).__name__}: {str(e)[:150]}"
        log.warning("tavily image search failed: %s", detail)
        _record("error", detail)
        return []
