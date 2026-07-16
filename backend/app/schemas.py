"""Pydantic schemas shared by the pipeline, API, and persistence layer."""

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=8000)


class QueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=8000)
    history: list[ChatTurn] = Field(default=[], max_length=20)


class Bid(BaseModel):
    model_key: str
    model_name: str
    confidence: float = 0.0
    estimated_difficulty: float = 0.5
    reason: str = ""
    historical_accuracy: float = 0.7
    cost_factor: float = 0.0          # normalized 0..1 across tier-1 models
    auction_score: float = 0.0
    error: Optional[str] = None       # set when a bidder failed / timed out
    draft_answer: Optional[str] = None  # speculative answer from a confident bidder


class Verification(BaseModel):
    score: float
    passed: bool
    feedback: str = ""


class Usage(BaseModel):
    model_key: str
    model_name: str
    stage: Literal["bid", "draft", "verify", "escalate"]
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0


class RunResult(BaseModel):
    id: str
    query: str
    answer: str
    answered_by: str                  # display name of the model that answered
    tier: Literal[1, 2]
    escalated: bool
    escalation_reason: Optional[str] = None
    bids: list[Bid] = []
    winner: Optional[str] = None      # model_key of auction winner
    draft_answer: Optional[str] = None
    verification: Optional[Verification] = None
    usages: list[Usage] = []
    total_cost_usd: float = 0.0
    baseline_cost_usd: float = 0.0    # what frontier-only would have cost
    latency_ms: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MetricsSummary(BaseModel):
    total_queries: int = 0
    avg_cost_usd: float = 0.0
    total_cost_usd: float = 0.0
    total_saved_usd: float = 0.0
    avg_latency_ms: int = 0
    escalation_rate: float = 0.0
    tier1_resolution_rate: float = 0.0
    wins_by_model: dict[str, int] = {}
    accuracy_by_model: dict[str, float] = {}
