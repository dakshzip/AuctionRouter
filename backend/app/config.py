"""Central configuration for AuctionRouter.

All model choices, auction weights, and thresholds from the PRD live here so
they can be tuned without touching pipeline code.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelSpec:
    """Static description of a model available through OpenRouter."""

    def __init__(self, key: str, openrouter_id: str, display_name: str,
                 cost_per_mtok_in: float, cost_per_mtok_out: float,
                 fallback_id: str | None = None, specialty: str = ""):
        self.key = key
        self.openrouter_id = openrouter_id
        self.display_name = display_name
        # One-line self-description injected into the bid prompt so the
        # model bids according to its actual strengths
        self.specialty = specialty
        # USD per 1M tokens: pricing of the PAID model in this slot (the
        # fallback when the primary is a free variant). Used for the auction
        # cost term and the savings metric.
        self.cost_per_mtok_in = cost_per_mtok_in
        self.cost_per_mtok_out = cost_per_mtok_out
        # Paid model tried automatically when the free primary is
        # rate-limited (OpenRouter `models` fallback routing)
        self.fallback_id = fallback_id

    def estimate_cost(self, tokens_in: int, tokens_out: int,
                      served_model: str | None = None) -> float:
        if served_model and served_model.endswith(":free"):
            return 0.0
        return (tokens_in * self.cost_per_mtok_in
                + tokens_out * self.cost_per_mtok_out) / 1_000_000


# --- Tier 1: cheap bidders -------------------------------------------------
TIER1_MODELS: dict[str, ModelSpec] = {
    # Bidders/verifier run free-first with an automatic paid fallback when
    # the free pool is rate-limited. Pricing fields = the paid fallback.
    "gemini": ModelSpec(
        key="gemini",
        openrouter_id="google/gemma-4-26b-a4b-it:free",
        fallback_id="google/gemini-2.5-flash-lite",
        display_name="Gemma 4 / Gemini Lite",
        cost_per_mtok_in=0.10,
        cost_per_mtok_out=0.40,
        specialty="a fast lightweight generalist: strong at general knowledge, "
                  "summaries, and everyday questions; NOT a code specialist and "
                  "weak at hard math proofs and complex multi-step reasoning — "
                  "defer those to the specialists",
    ),
    "deepseek": ModelSpec(
        key="deepseek",
        openrouter_id="deepseek/deepseek-chat",  # no free variant; cheapest paid
        display_name="DeepSeek",
        cost_per_mtok_in=0.20,
        cost_per_mtok_out=0.80,
        specialty="strongest at mathematical reasoning, logic puzzles, and "
                  "quantitative problems",
    ),
    "qwen": ModelSpec(
        key="qwen",
        openrouter_id="qwen/qwen3-coder:free",
        fallback_id="qwen/qwen3-coder",
        display_name="Qwen3 Coder",
        cost_per_mtok_in=0.22,
        cost_per_mtok_out=1.80,
        specialty="a coding specialist: strongest at writing, debugging, and "
                  "explaining code and software architecture; weaker at "
                  "non-technical general knowledge",
    ),
}

# --- Verifier ---------------------------------------------------------------
VERIFIER_MODEL = ModelSpec(
    key="verifier",
    openrouter_id="openai/gpt-oss-120b",
    display_name="GPT-OSS 120B (Verifier)",
    cost_per_mtok_in=0.04,
    cost_per_mtok_out=0.17,
)

# --- Tier 2: frontier escalation target -------------------------------------
TIER2_MODEL = ModelSpec(
    key="frontier",
    openrouter_id="openai/gpt-5",
    display_name="GPT-5",
    cost_per_mtok_in=1.25,
    cost_per_mtok_out=10.00,
)

# Baseline used for "cost saved" metrics: what the query would have cost if
# every request went straight to the frontier model.
BASELINE_MODEL = TIER2_MODEL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    # Provider routing preference: "latency" | "throughput" | "price";
    # empty string keeps OpenRouter's default (price)
    openrouter_provider_sort: str = "latency"

    mongodb_uri: str = ""          # empty -> in-memory store
    mongodb_db: str = "auctionrouter"

    # Auction score = 0.7*confidence + 0.2*historical_accuracy - 0.1*cost
    auction_w_confidence: float = 0.7
    auction_w_history: float = 0.2
    auction_w_cost: float = 0.1

    # Escalation thresholds (PRD section 9)
    # Pre-filter only — the verifier still gates every tier-1 draft, so
    # this can be loose; it exists to skip drafting obviously-doomed answers
    min_auction_confidence: float = 0.65
    verification_threshold: float = 0.80
    disagreement_stddev: float = 0.22
    # Skip the disagreement check when some bidder is at least this
    # confident (specialists legitimately disagree with generalists)
    disagreement_exempt_confidence: float = 0.85

    # Default historical accuracy for models with no track record yet
    default_historical_accuracy: float = 0.70

    request_timeout_s: float = 60.0
    bid_timeout_s: float = 20.0
    # Once a confident bid is in hand, stragglers get this much longer
    # before the auction proceeds without them
    bid_grace_s: float = 2.0

    # Bidders at or above this confidence append a speculative answer to
    # their bid, letting the pipeline skip the separate draft round-trip
    speculative_draft_confidence: float = 0.8

    # Cap completion size so a single answer can't blow the budget
    # (also keeps low-credit OpenRouter keys usable)
    max_answer_tokens: int = 2000
    # Bids without a speculative answer stay ~100 tokens; the cap only
    # bites on answer-carrying bids
    max_bid_tokens: int = 1600

    # Conversation history caps per pipeline stage (turns are single
    # messages, so 4 turns = 2 user/assistant exchanges)
    history_max_turns_bid: int = 4
    history_max_chars_bid: int = 1600
    history_max_turns_answer: int = 12
    history_max_chars_answer: int = 12000
    history_max_turns_verify: int = 6
    history_max_chars_verify: int = 4000
    # Frontier headroom: reasoning tokens count against the cap (medium
    # effort thinks longer than low), so don't cut this too far or the
    # answer comes back empty
    max_frontier_tokens: int = 8000
    # Easy escalations think little at low effort, so a smaller cap is
    # safe and bounds the worst-case bill; keep enough headroom that
    # reasoning + answer never hits it (empty-response failure mode)
    max_frontier_tokens_easy: int = 3000
    frontier_reasoning_effort: str = "medium"
    # Adaptive effort: escalations whose bids rated the query below this
    # mean estimated_difficulty use the easy effort — they're escalations
    # of convenience (failed verification on an easy query), not hard ones
    frontier_difficulty_threshold: float = 0.6
    frontier_easy_reasoning_effort: str = "low"
    # Low effort keeps the verifier honest on easy answers without
    # spending 8s of chain-of-thought on a greeting
    verifier_reasoning_effort: str = "low"


settings = Settings()
