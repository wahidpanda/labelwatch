from datetime import date

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LlmBudget, TraceBudget


class BudgetRepository:
    """Counters for free-tier quotas: LLM calls per day and LangSmith traces per month."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def llm_calls(self, day: date, provider: str) -> int:
        total = await self._session.scalar(
            select(func.coalesce(func.sum(LlmBudget.calls), 0)).where(
                LlmBudget.day == day, LlmBudget.provider == provider
            )
        )
        return int(total or 0)

    async def record_llm_call(
        self, day: date, provider: str, model: str, *, tokens_in: int, tokens_out: int
    ) -> None:
        stmt = insert(LlmBudget).values(
            day=day,
            provider=provider,
            model=model,
            calls=1,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )
        await self._session.execute(
            stmt.on_conflict_do_update(
                index_elements=[LlmBudget.day, LlmBudget.provider, LlmBudget.model],
                set_={
                    "calls": LlmBudget.calls + 1,
                    "tokens_in": LlmBudget.tokens_in + stmt.excluded.tokens_in,
                    "tokens_out": LlmBudget.tokens_out + stmt.excluded.tokens_out,
                },
            )
        )

    async def traces(self, month: date) -> int:
        value = await self._session.scalar(
            select(TraceBudget.traces).where(TraceBudget.month == month)
        )
        return int(value or 0)

    async def increment_traces(self, month: date) -> int:
        stmt = insert(TraceBudget).values(month=month, traces=1)
        result = await self._session.scalar(
            stmt.on_conflict_do_update(
                index_elements=[TraceBudget.month],
                set_={"traces": TraceBudget.traces + 1},
            ).returning(TraceBudget.traces)
        )
        return int(result or 0)

    async def database_size_mb(self) -> float:
        size = await self._session.scalar(text("select pg_database_size(current_database())"))
        return int(size or 0) / (1024 * 1024)
