"""Run persistence + metrics. Uses MongoDB when MONGODB_URI is set,
otherwise an in-memory store so the app works with zero setup."""

from collections import defaultdict
from typing import Optional

from .config import settings
from .schemas import MetricsSummary, RunResult


class BaseStore:
    async def save_run(self, run: RunResult) -> None: ...
    async def list_runs(self, limit: int = 50) -> list[RunResult]: ...
    async def historical_accuracy(self) -> dict[str, float]: ...
    async def metrics(self) -> MetricsSummary: ...


class MemoryStore(BaseStore):
    def __init__(self) -> None:
        self._runs: list[RunResult] = []

    async def save_run(self, run: RunResult) -> None:
        self._runs.append(run)

    async def list_runs(self, limit: int = 50) -> list[RunResult]:
        return list(reversed(self._runs[-limit:]))

    async def historical_accuracy(self) -> dict[str, float]:
        return _accuracy_from_runs(self._runs)

    async def metrics(self) -> MetricsSummary:
        return _metrics_from_runs(self._runs)


class MongoStore(BaseStore):
    def __init__(self, uri: str, db_name: str) -> None:
        from motor.motor_asyncio import AsyncIOMotorClient
        self._col = AsyncIOMotorClient(uri)[db_name]["runs"]

    async def save_run(self, run: RunResult) -> None:
        await self._col.insert_one(run.model_dump(mode="json"))

    async def list_runs(self, limit: int = 50) -> list[RunResult]:
        docs = await self._col.find({}, {"_id": 0}).sort("created_at", -1).to_list(limit)
        return [RunResult.model_validate(d) for d in docs]

    async def _all_runs(self) -> list[RunResult]:
        docs = await self._col.find({}, {"_id": 0}).to_list(10_000)
        return [RunResult.model_validate(d) for d in docs]

    async def historical_accuracy(self) -> dict[str, float]:
        return _accuracy_from_runs(await self._all_runs())

    async def metrics(self) -> MetricsSummary:
        return _metrics_from_runs(await self._all_runs())


def _accuracy_from_runs(runs: list[RunResult]) -> dict[str, float]:
    """Fraction of a model's drafts that passed verification.

    This feeds the 'historical accuracy' term of the auction score.
    """
    attempts: dict[str, int] = defaultdict(int)
    passes: dict[str, int] = defaultdict(int)
    for run in runs:
        if run.winner and run.verification is not None:
            attempts[run.winner] += 1
            if run.verification.passed:
                passes[run.winner] += 1
    return {m: passes[m] / attempts[m] for m in attempts}


def _metrics_from_runs(runs: list[RunResult]) -> MetricsSummary:
    if not runs:
        return MetricsSummary()
    n = len(runs)
    total_cost = sum(r.total_cost_usd for r in runs)
    baseline = sum(r.baseline_cost_usd for r in runs)
    escalated = sum(1 for r in runs if r.escalated)
    wins: dict[str, int] = defaultdict(int)
    for r in runs:
        if r.winner:
            wins[r.winner] += 1
    return MetricsSummary(
        total_queries=n,
        avg_cost_usd=total_cost / n,
        total_cost_usd=total_cost,
        total_saved_usd=max(baseline - total_cost, 0.0),
        avg_latency_ms=int(sum(r.latency_ms for r in runs) / n),
        escalation_rate=escalated / n,
        tier1_resolution_rate=1 - escalated / n,
        wins_by_model=dict(wins),
        accuracy_by_model=_accuracy_from_runs(runs),
    )


_store: Optional[BaseStore] = None


def get_store() -> BaseStore:
    global _store
    if _store is None:
        if settings.mongodb_uri:
            _store = MongoStore(settings.mongodb_uri, settings.mongodb_db)
        else:
            _store = MemoryStore()
    return _store
