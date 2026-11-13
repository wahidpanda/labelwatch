import random
from datetime import date

import pytest

from app.core.budget import (
    TRACE_HARD_LIMIT,
    TRACE_SOFT_LIMIT,
    BudgetExceededError,
    DatabaseSizeExceededError,
    TraceKind,
    check_llm_budget,
    ensure_database_capacity,
    month_start,
    record_llm_usage,
    should_trace,
)

TODAY = date(2026, 11, 13)


class FakeBudgetStore:
    def __init__(self, *, size_mb: float = 10.0, calls: int = 0) -> None:
        self.size_mb = size_mb
        self.calls = calls
        self.recorded: list[tuple[str, str, int, int]] = []
        self.trace_count = 0

    async def llm_calls(self, day: date, provider: str) -> int:
        return self.calls

    async def record_llm_call(
        self, day: date, provider: str, model: str, *, tokens_in: int, tokens_out: int
    ) -> None:
        self.calls += 1
        self.recorded.append((provider, model, tokens_in, tokens_out))

    async def traces(self, month: date) -> int:
        return self.trace_count

    async def increment_traces(self, month: date) -> int:
        self.trace_count += 1
        return self.trace_count

    async def database_size_mb(self) -> float:
        return self.size_mb


@pytest.mark.parametrize(("size_mb", "blocked"), [(10.0, False), (399.9, False), (400.0, True)])
async def test_database_size_guard(size_mb: float, blocked: bool) -> None:
    store = FakeBudgetStore(size_mb=size_mb)
    if blocked:
        with pytest.raises(DatabaseSizeExceededError, match="400 MB"):
            await ensure_database_capacity(store, limit_mb=400)
    else:
        assert await ensure_database_capacity(store, limit_mb=400) == size_mb


async def test_llm_budget_allows_until_cap_then_raises() -> None:
    store = FakeBudgetStore(calls=0)
    for _ in range(3):
        await check_llm_budget(store, "groq", cap=3, today=TODAY)
        await record_llm_usage(store, "groq", "m", TODAY, tokens_in=10, tokens_out=2)
    with pytest.raises(BudgetExceededError) as excinfo:
        await check_llm_budget(store, "groq", cap=3, today=TODAY)
    assert excinfo.value.calls == 3
    assert store.recorded[0] == ("groq", "m", 10, 2)


def test_month_start() -> None:
    assert month_start(TODAY) == date(2026, 11, 1)


@pytest.mark.parametrize(
    ("kind", "count", "expected"),
    [
        (TraceKind.ASSISTANT, 0, True),
        (TraceKind.EVAL, 0, True),
        (TraceKind.ASSISTANT, TRACE_SOFT_LIMIT, False),
        (TraceKind.ERROR, TRACE_SOFT_LIMIT, True),
        (TraceKind.EVAL, TRACE_SOFT_LIMIT, True),
        (TraceKind.BATCH, TRACE_SOFT_LIMIT, False),
        (TraceKind.ERROR, TRACE_HARD_LIMIT, False),
        (TraceKind.EVAL, TRACE_HARD_LIMIT, False),
        (TraceKind.ADMIN, TRACE_HARD_LIMIT, True),
    ],
)
def test_trace_policy_tiers(kind: TraceKind, count: int, expected: bool) -> None:
    assert should_trace(kind, count, sample_rate=1.0) is expected


def test_batch_traces_are_sampled() -> None:
    rng = random.Random(42)
    sampled = sum(should_trace(TraceKind.BATCH, 0, 0.2, rng) for _ in range(10_000))
    assert 1_800 < sampled < 2_200
    assert should_trace(TraceKind.BATCH, 0, 0.0) is False
