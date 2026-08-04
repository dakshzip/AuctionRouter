"""No-network guards for the Tavily image search.

The feature is best-effort by contract: every failure path must return an
empty list rather than raise, because an image lookup must never be able to
break or delay an answer.
"""
import httpx
import pytest

from app import websearch
from app.config import settings
from app.websearch import _parse, search_images, search_subject

PAYLOAD = {
    "images": [
        {"url": "https://a.example/1.jpg", "description": "a photo"},
        {"url": "https://a.example/1.jpg", "description": "dupe"},
        {"url": "", "description": "no url"},
        {"url": "ftp://a.example/3.jpg", "description": "wrong scheme"},
        # plain http would be blocked as mixed content on the TLS deployment
        {"url": "http://a.example/5.jpg", "description": "insecure"},
        {"url": "https://a.example/2.jpg", "description": "x" * 500},
        "https://a.example/4.jpg",  # bare string (no image descriptions)
    ],
}


def test_parse_filters_and_dedupes():
    out = _parse(PAYLOAD, limit=10)
    assert [i.url for i in out] == [
        "https://a.example/1.jpg",
        "https://a.example/2.jpg",
        "https://a.example/4.jpg",
    ]
    assert len(out[1].description) == 200      # truncated
    assert out[2].description == ""            # bare string -> no description


def test_parse_respects_limit():
    assert len(_parse(PAYLOAD, limit=2)) == 2


def test_parse_tolerates_missing_key():
    assert _parse({}, limit=3) == []


@pytest.mark.parametrize("query,expected", [
    # scaffolding stripped
    ("show me photos of the new iPhone 17", "the new iPhone 17"),
    ("what does the newest iphone model look like", "the newest iphone model"),
    ("What do red pandas look like?", "red pandas"),
    ("pictures of mount fuji", "mount fuji"),
    # a leading article gets absorbed with the scaffolding; harmless for search
    ("can you show me the tesla roadster", "tesla roadster"),
    ("i wanna see pics of the eiffel tower", "the eiffel tower"),
    # already a clean subject — left alone
    ("who is the current prime minister of japan",
     "who is the current prime minister of japan"),
    ("best places to visit in kyoto right now",
     "best places to visit in kyoto right now"),
    # all scaffolding, no subject -> fall back to the original
    ("show me photos", "show me photos"),
])
def test_search_subject(query, expected):
    assert search_subject(query) == expected


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr(settings, "tavily_api_key", "tvly-test")
    monkeypatch.setattr(settings, "image_search_enabled", True)


def _stub(monkeypatch, handler):
    """Point websearch's module client at a mock transport."""
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(websearch, "_client", client)


@pytest.mark.asyncio
async def test_search_images_happy_path(monkeypatch, enabled):
    _stub(monkeypatch, lambda req: httpx.Response(200, json=PAYLOAD))
    out = await search_images("mount fuji", limit=3)
    assert len(out) == 3
    assert out[0].url == "https://a.example/1.jpg"


@pytest.mark.asyncio
async def test_search_images_swallows_http_error(monkeypatch, enabled):
    _stub(monkeypatch, lambda req: httpx.Response(500, text="boom"))
    assert await search_images("mount fuji") == []


@pytest.mark.asyncio
async def test_search_images_swallows_timeout(monkeypatch, enabled):
    def handler(req):
        raise httpx.ReadTimeout("too slow", request=req)

    _stub(monkeypatch, handler)
    assert await search_images("mount fuji") == []


@pytest.mark.asyncio
async def test_search_images_swallows_bad_json(monkeypatch, enabled):
    _stub(monkeypatch, lambda req: httpx.Response(200, text="not json"))
    assert await search_images("mount fuji") == []


@pytest.mark.asyncio
async def test_disabled_without_key(monkeypatch):
    monkeypatch.setattr(settings, "tavily_api_key", "")
    # No transport stub: a real call would fail the test by hanging/erroring
    assert await search_images("mount fuji") == []
    assert not websearch.enabled()


@pytest.mark.asyncio
async def test_empty_query_short_circuits(monkeypatch, enabled):
    assert await search_images("   ") == []
