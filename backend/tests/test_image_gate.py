"""The image gate: the visual-intent regex, and its AND with the web search."""
import pytest

from app.pipeline import _wants_images_heuristic, auction
from app.schemas import Bid

# --- queries a photograph would genuinely serve ------------------------------
VISUAL = [
    # explicit asks
    "show me photos of the new iPhone 17",
    "what does the newest iphone model look like",
    "pictures of mount fuji",
    "i wanna see the tesla roadster",
    # named people in a role — the case bidders kept missing
    "who is the current prime minister of japan",
    "who is sanae takaichi",
    "who's the new ceo of intel",
    # events people watch happen
    "latest spacex starship launch",
    "who won the super bowl this year",
    "who won the game",
    "world cup final result",
    # places and built things
    "best places to visit in kyoto right now",
    "tallest bridge in the world",
]

# --- queries where photos would be filler ------------------------------------
NOT_VISUAL = [
    "bitcoin price today",
    "price of the new iphone",           # names a photogenic thing, wants a number
    "what's the weather in tokyo right now",
    "when is the next solar eclipse",    # photogenic subject, but wants a date
    "write a python function to reverse a linked list",
    "explain how tcp handshakes work",
    "what does this error message mean",
    "how to make sourdough",
    "define entropy",
    "derivative of x squared",
]


@pytest.mark.parametrize("q", VISUAL)
def test_visual_queries_fire(q):
    assert _wants_images_heuristic(q) is True, q


@pytest.mark.parametrize("q", NOT_VISUAL)
def test_non_visual_queries_do_not_fire(q):
    assert _wants_images_heuristic(q) is False, q


def test_negative_patterns_beat_positive_ones():
    # "price" wins over "new model of", so this stays a number question
    assert _wants_images_heuristic("price of the new model of iphone") is False


def _bid(**kw) -> Bid:
    base = dict(model_key="gpt-oss", model_name="GPT-OSS 120B",
                confidence=0.9, estimated_difficulty=0.2)
    return Bid(**{**base, **kw})


async def _run(query: str, **bid_kw) -> dict:
    return await auction({"query": query, "bids": [_bid(**bid_kw)]})


@pytest.mark.asyncio
async def test_any_bidder_can_ask_for_images():
    # The winner didn't want images but a losing bidder did — bidders
    # disagree on the same query, so one yes is enough.
    out = await auction({"query": "who is sanae takaichi", "bids": [
        _bid(confidence=0.9, needs_web=True, wants_images=False),
        _bid(model_key="deepseek", confidence=0.6,
             needs_web=True, wants_images=True),
    ]})
    assert out["winner"] == "gpt-oss"
    assert out["wants_images"] is True


@pytest.mark.asyncio
async def test_wants_images_needs_a_web_search():
    # Timeless query -> no web search -> no images, even though the bidder
    # asked for them.
    out = await _run("what is a red panda", wants_images=True, needs_web=False)
    assert out["needs_web"] is False
    assert out["wants_images"] is False


@pytest.mark.asyncio
async def test_wants_images_passes_through_on_web_queries():
    out = await _run("who is the current prime minister of japan",
                     wants_images=True, needs_web=True)
    assert out["needs_web"] is True
    assert out["wants_images"] is True


@pytest.mark.asyncio
async def test_web_query_without_the_flag_gets_no_images():
    out = await _run("bitcoin price today", wants_images=False, needs_web=True)
    assert out["needs_web"] is True
    assert out["wants_images"] is False
