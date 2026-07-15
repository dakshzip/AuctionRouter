"""Central configuration for AuctionRouter.

All model choices, auction weights, and thresholds from the PRD live here so
they can be tuned without touching pipeline code.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelSpec:
    """Static description of a model available through OpenRouter."""

    def __init__(self, key: str, openrouter_id: str, display_name: str,
                 cost_per_mtok_in: float, cost_per_mtok_out: float):
        self.key = key
        self.openrouter_id = openrouter_id
        self.display_name = display_name
        # USD per 1M tokens (approximate OpenRouter pricing, used for the
        # auction cost term and the savings metric)
        self.cost_per_mtok_in = cost_per_mtok_in
        self.cost_per_mtok_out = cost_per_mtok_out

    def estimate_cost(self, tokens_in: int, tokens_out: int) -> float:
        return (tokens_in * self.cost_per_mtok_in
                + tokens_out * self.cost_per_mtok_out) / 1_000_000


# --- Tier 1: cheap bidders -------------------------------------------------
TIER1_MODELS: dict[str, ModelSpec] = {
    "gemma": ModelSpec(
        key="gemma",
        openrouter_id="google/gemma-4-26b-a4b-it:free",
        display_name="Gemma 4 26B",
        cost_per_mtok_in=0.0,
        cost_per_mtok_out=0.0,
    ),
    "deepseek": ModelSpec(
        key="deepseek",
        openrouter_id="deepseek/deepseek-chat",
        display_name="DeepSeek",
        cost_per_mtok_in=0.20,
        cost_per_mtok_out=0.80,
    ),
    # Non-thinking instruct variant: thinking models burn the whole
    # max_tokens budget on hidden reasoning and return empty content
    "qwen": ModelSpec(
        key="qwen",
        openrouter_id="qwen/qwen3-next-80b-a3b-instruct:free",
        display_name="Qwen3 Next 80B",
        cost_per_mtok_in=0.0,
        cost_per_mtok_out=0.0,
    ),
}

# --- Verifier ---------------------------------------------------------------
VERIFIER_MODEL = ModelSpec(
    key="verifier",
    openrouter_id="google/gemma-4-31b-it:free",
    display_name="Gemma 4 31B (Verifier)",
    cost_per_mtok_in=0.0,
    cost_per_mtok_out=0.0,
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

    mongodb_uri: str = ""          # empty -> in-memory store
    mongodb_db: str = "auctionrouter"

    # Auction score = 0.7*confidence + 0.2*historical_accuracy - 0.1*cost
    auction_w_confidence: float = 0.7
    auction_w_history: float = 0.2
    auction_w_cost: float = 0.1

    # Escalation thresholds (PRD section 9)
    min_auction_confidence: float = 0.75
    verification_threshold: float = 0.80
    disagreement_stddev: float = 0.22

    # Default historical accuracy for models with no track record yet
    default_historical_accuracy: float = 0.70

    request_timeout_s: float = 60.0
    bid_timeout_s: float = 20.0

    # Cap completion size so a single answer can't blow the budget
    # (also keeps low-credit OpenRouter keys usable)
    max_answer_tokens: int = 2000
    max_bid_tokens: int = 300
    # Frontier gets extra headroom since reasoning tokens count against
    # the cap even at low effort
    max_frontier_tokens: int = 4000


settings = Settings()
