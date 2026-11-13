"""Guards for free-tier limits: database size, daily LLM calls, monthly LangSmith traces."""

import random
from datetime import date
from enum import StrEnum
from typing import Protocol

TRACE_SOFT_LIMIT = 4_000
TRACE_HARD_LIMIT = 4_800


class DatabaseSizeExceededError(RuntimeError):
    def __init__(self, size_mb: float, limit_mb: int) -> None:
        super().__init__(f"Database is {size_mb:.1f} MB, above the {limit_mb} MB ingestion limit.")
        self.size_mb = size_mb
        self.limit_mb = limit_mb


class BudgetExceededError(RuntimeError):
    def __init__(self, provider: str, calls: int, cap: int) -> None:
        super().__init__(f"Daily LLM cap reached for {provider}: {calls}/{cap} calls.")
        self.provider = provider
        self.calls = calls
        self.cap = cap


class BudgetStore(Protocol):
    async def llm_calls(self, day: date, provider: str) -> int: ...

    async def record_llm_call(
        self, day: date, provider: str, model: str, *, tokens_in: int, tokens_out: int
    ) -> None: ...

    async def traces(self, month: date) -> int: ...

    async def increment_traces(self, month: date) -> int: ...

    async def database_size_mb(self) -> float: ...


async def ensure_database_capacity(store: BudgetStore, limit_mb: int) -> float:
    """Raise before ingestion writes more data once the database passes the limit."""
    size_mb = await store.database_size_mb()
    if size_mb >= limit_mb:
        raise DatabaseSizeExceededError(size_mb, limit_mb)
    return size_mb


async def check_llm_budget(store: BudgetStore, provider: str, cap: int, today: date) -> int:
    """Return calls used today, or raise if the provider's daily cap is reached."""
    calls = await store.llm_calls(today, provider)
    if calls >= cap:
        raise BudgetExceededError(provider, calls, cap)
    return calls


async def record_llm_usage(
    store: BudgetStore,
    provider: str,
    model: str,
    today: date,
    *,
    tokens_in: int,
    tokens_out: int,
) -> None:
    await store.record_llm_call(today, provider, model, tokens_in=tokens_in, tokens_out=tokens_out)


class TraceKind(StrEnum):
    BATCH = "batch"
    ASSISTANT = "assistant"
    EVAL = "eval"
    ERROR = "error"
    ADMIN = "admin"


def month_start(day: date) -> date:
    return day.replace(day=1)


def should_trace(
    kind: TraceKind,
    traces_this_month: int,
    sample_rate: float,
    rng: random.Random | None = None,
) -> bool:
    """Apply the section 11.5 rules for one root trace."""
    if traces_this_month >= TRACE_HARD_LIMIT:
        return kind is TraceKind.ADMIN
    if traces_this_month >= TRACE_SOFT_LIMIT:
        return kind in {TraceKind.ERROR, TraceKind.EVAL, TraceKind.ADMIN}
    if kind is TraceKind.BATCH:
        return (rng or random.Random()).random() < sample_rate  # noqa: S311 - sampling, not crypto
    return True
