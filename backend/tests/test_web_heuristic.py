"""Fast, no-API guards for the web-need detection heuristics.

Pins the behaviour of the t=0 regex gate (`_needs_web_heuristic`) and the
draft-uncertainty fallback (`_admits_no_fresh_info`) so `_WEB_KEYWORDS` can be
grown for recall without silently regressing on the discourse/homonym traps.
"""
import pytest

from app.pipeline import _admits_no_fresh_info, _needs_web_heuristic

# --- queries that SHOULD trigger a web search -------------------------------
NEEDS_WEB = [
    "what's the weather in Tokyo right now",
    "who is the current president of the US",
    "latest iPhone release date",
    "bitcoin price today",
    "who won the game last night",
    "news about the election",
    "what happened this week in tech",
    "stock price of Tesla",
    "is Cloudflare down",
    "current CEO of OpenAI",
    "trending songs this month",
    "the 2025 F1 standings",          # year >= cutoff
    "events in 2026",                  # year >= cutoff
    "how much does a PS5 cost now",
    "most recent SpaceX launch",
    "who's winning the match",
    "weather forecast for London",
    "who is the reigning Wimbledon champion",
    "who holds the marathon world record",
    # current-state questions (answer drifts even with no recency word)
    "who is the president of France",
    "who is the CEO of Anthropic",
    "how old is Messi",
    "net worth of Elon Musk",
    "what time is it in Tokyo",
    "did Arsenal win",
    # unambiguous temporal anchors
    "what happened yesterday",
    "is the game tomorrow",
]

# --- queries that SHOULD NOT trigger (evergreen + discourse/homonym traps) ---
NO_WEB = [
    "what is the capital of France",
    "explain how photosynthesis works",
    "write a poem about the sea",
    "what is 2+2",
    "who was president in 1990",        # historical year < cutoff
    "history of the Roman empire",
    "reverse a linked list in Python",
    "what year did WWII end in 1945",
    "summarize Hamlet",
    "now let's do the next step",       # discourse "now"
    "I'm currently learning Python, explain decorators",  # discourse "currently"
    "explain electric current",         # homonym "current"
    "what is a musical score",          # homonym "score"
    "explain how bitcoin works",        # evergreen, not "bitcoin price"
    "how much is 2+2",                  # math, not a price question
    "how much is 500ml in cups",        # unit conversion
    "who is the president in the book 1984",  # pre-cutoff year -> history
    "who was the king of France in 1789",     # pre-cutoff year -> history
]

# --- drafts that admit they lack fresh info (fallback SHOULD fire) ----------
ADMITS = [
    "As of my last training update, the CEO was Bob.",
    "That event hasn't happened yet, so I can't say who won.",
    "I don't have access to real-time data, so I can't give the current price.",
    "I'm not sure about the very latest version.",
    "My knowledge cutoff is 2024, so this may have changed since.",
    "For the latest figures, check the official website.",
    "I cannot browse the internet to get current results.",
    "I don't have that information available.",
]

# --- confident drafts (fallback SHOULD NOT fire) ---------------------------
CLEAN = [
    "The capital of France is Paris.",
    "Photosynthesis converts light into chemical energy.",
    "Here is a Python function to reverse a linked list.",
    "The answer is 42.",
    "Sure! Here's a short poem about the sea.",
]


@pytest.mark.parametrize("q", NEEDS_WEB)
def test_needs_web_fires(q):
    assert _needs_web_heuristic(q) is True, q


@pytest.mark.parametrize("q", NO_WEB)
def test_needs_web_silent(q):
    assert _needs_web_heuristic(q) is False, q


@pytest.mark.parametrize("t", ADMITS)
def test_admission_fires(t):
    assert _admits_no_fresh_info(t) is True, t


@pytest.mark.parametrize("t", CLEAN)
def test_admission_silent(t):
    assert _admits_no_fresh_info(t) is False, t
