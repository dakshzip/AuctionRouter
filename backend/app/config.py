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
    "deepseek": ModelSpec(  # general
        key="deepseek",
        openrouter_id="deepseek/deepseek-v4-flash:free",
        fallback_id="deepseek/deepseek-v4-flash",
        display_name="DeepSeek V4 Flash",
        cost_per_mtok_in=0.09,
        cost_per_mtok_out=0.18,
        specialty="a fast, capable generalist: general knowledge, writing, "
                  "summaries, and everyday questions; solid all-rounder "
                  "across most topics",
    ),
    "qwen": ModelSpec(  # coding
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
    "nemotron": ModelSpec(  # math / reasoning
        key="nemotron",
        openrouter_id="nvidia/nemotron-3-ultra-550b-a55b:free",
        fallback_id="nvidia/nemotron-3-ultra-550b-a55b",
        display_name="Nemotron 3 Ultra",
        cost_per_mtok_in=0.60,
        cost_per_mtok_out=3.60,
        specialty="strongest at mathematical reasoning, logic puzzles, "
                  "quantitative problems, and hard multi-step reasoning; "
                  "a large capable reasoner",
    ),
}

# Topic toggle -> which tier-1 model drafts speculatively during bidding.
# If the auction then picks that model, its draft is already in flight.
SPECULATIVE_HINT_MODELS: dict[str, str] = {
    "general": "deepseek",
    "coding": "qwen",
    "reasoning": "nemotron",
}

# --- Verifier ---------------------------------------------------------------
VERIFIER_MODEL = ModelSpec(
    key="verifier",
    openrouter_id="tencent/hy3",
    display_name="Tencent Hy3 (Verifier)",
    cost_per_mtok_in=0.20,
    cost_per_mtok_out=0.80,
)

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    # Provider routing preference: "latency" | "throughput" | "price";
    # empty string keeps OpenRouter's default (price)
    openrouter_provider_sort: str = "latency"

    # --- Deployment / abuse protection --------------------------------------
    # Shared access code required on every /api/* request (X-Access-Code
    # header). Empty string disables the gate (local dev convenience).
    access_code: str = ""
    # Comma-separated browser origins allowed by CORS (localhost + the
    # deployed frontend). NOT a security boundary — curl ignores CORS.
    allowed_origins: str = "http://localhost:3000"
    # Hard daily spend ceiling (USD, UTC day). Query endpoints 503 once
    # exceeded. The credit-capped OpenRouter key is the true backstop.
    daily_spend_limit_usd: float = 20.0
    # Per-IP rate limits on the query endpoints
    rate_limit_per_min: int = 15
    rate_limit_per_day: int = 150

    mongodb_uri: str = ""          # empty -> in-memory store
    mongodb_db: str = "auctionrouter"

    # Auction score = 0.7*confidence + 0.2*historical_accuracy - 0.1*cost
    auction_w_confidence: float = 0.7
    auction_w_history: float = 0.2
    auction_w_cost: float = 0.1

    # Escalation thresholds (PRD section 9)
    # Pre-filter only — the verifier still gates every tier-1 draft, so
    # this can be loose; it exists to skip drafting obviously-doomed
    # answers (genuinely hard queries bid 0.2-0.4)
    min_auction_confidence: float = 0.55
    verification_threshold: float = 0.80
    # Specialist bidders legitimately disagree on everyday queries; only a
    # drastic spread with nobody confident should escalate pre-draft
    disagreement_stddev: float = 0.30

    # HARD GATE: GPT-5 is reserved for hard STEM/coding/reasoning queries
    # (mean bid estimated_difficulty at or above this). Everything else
    # NEVER escalates — a failed verification ships the tier-1 draft
    # marked unverified instead of summoning the frontier.
    escalation_min_difficulty: float = 0.6
    # Skip the disagreement check when some bidder is at least this
    # confident (specialists legitimately disagree with generalists)
    disagreement_exempt_confidence: float = 0.85

    # Default historical accuracy for models with no track record yet
    default_historical_accuracy: float = 0.70

    request_timeout_s: float = 60.0
    bid_timeout_s: float = 20.0

    # Bidders at or above this confidence append a speculative answer to
    # their bid, letting the pipeline skip the separate draft round-trip
    speculative_draft_confidence: float = 0.8

    # The user's topic toggle wins the auction outright when its model
    # bids at least this confidently; below it, normal auction rules
    hint_priority_confidence: float = 0.8

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
    # Escalations are rare now (hint-priority routing + calibrated bids
    # resolve most queries at tier 1), so the hard ones that do reach
    # GPT-5 get full thinking headroom
    max_frontier_tokens: int = 16000
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

    # Frontier (tier-2) model, overridable via FRONTIER_MODEL_ID — evals
    # swap in a big-but-cheap open model to avoid GPT-5 bills
    frontier_model_id: str = "openai/gpt-5"


settings = Settings()


# --- Tier 2: frontier escalation target -------------------------------------
# (display name, $/Mtok in, $/Mtok out) per known frontier choice; unknown
# ids fall back to GPT-5 pricing so cost metrics stay conservative
_FRONTIER_SPECS: dict[str, tuple[str, float, float]] = {
    "openai/gpt-5": ("GPT-5", 1.25, 10.00),
    "deepseek/deepseek-r1": ("DeepSeek R1", 0.50, 2.15),
    "meta-llama/llama-4-maverick": ("Llama 4 Maverick", 0.15, 0.60),
    "qwen/qwen3-235b-a22b": ("Qwen3 235B", 0.20, 0.60),
}
_name, _cin, _cout = _FRONTIER_SPECS.get(
    settings.frontier_model_id, (settings.frontier_model_id, 1.25, 10.00))
TIER2_MODEL = ModelSpec(
    key="frontier",
    openrouter_id=settings.frontier_model_id,
    display_name=_name,
    cost_per_mtok_in=_cin,
    cost_per_mtok_out=_cout,
)

# Baseline used for "cost saved" metrics: what the query would have cost if
# every request went straight to the frontier model.
BASELINE_MODEL = TIER2_MODEL
