from datetime import UTC, date, datetime

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import IngestionRun, LlmBudget, LlmCache, TraceBudget


class ProviderUsage(BaseModel):
    provider: str
    model: str
    calls: int
    tokens_in: int
    tokens_out: int


class LlmOpsOverview(BaseModel):
    as_of: datetime
    today: date
    trace_month: date
    traces_this_month: int
    langsmith_tracing: bool
    langsmith_project: str
    langsmith_url: str | None
    cache_entries: int
    cache_by_task: dict[str, int]
    usage_today: list[ProviderUsage]
    last_ingestion_at: datetime | None


class OpsService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    async def llm_overview(self) -> LlmOpsOverview:
        today = datetime.now(UTC).date()
        month = today.replace(day=1)
        rows = await self._session.execute(
            select(LlmBudget).where(LlmBudget.day == today).order_by(LlmBudget.provider)
        )
        usage = [
            ProviderUsage(
                provider=r.provider,
                model=r.model,
                calls=r.calls,
                tokens_in=int(r.tokens_in),
                tokens_out=int(r.tokens_out),
            )
            for r in rows.scalars()
        ]
        task_rows = await self._session.execute(
            select(LlmCache.task, func.count()).group_by(LlmCache.task)
        )
        cache_by_task = {task: int(count) for task, count in task_rows.all()}
        cache_total = int(
            await self._session.scalar(select(func.count()).select_from(LlmCache)) or 0
        )
        traces = int(
            await self._session.scalar(select(TraceBudget.traces).where(TraceBudget.month == month))
            or 0
        )
        last_run = await self._session.scalar(
            select(IngestionRun.finished_at)
            .where(IngestionRun.status.in_(("done", "partial")))
            .order_by(IngestionRun.finished_at.desc().nullslast())
            .limit(1)
        )
        project = self._settings.langsmith_project
        url = (
            f"https://smith.langchain.com/o/-/projects/p/{project}"
            if self._settings.langsmith_tracing
            else None
        )
        return LlmOpsOverview(
            as_of=datetime.now(UTC),
            today=today,
            trace_month=month,
            traces_this_month=traces,
            langsmith_tracing=self._settings.langsmith_tracing,
            langsmith_project=project,
            langsmith_url=url,
            cache_entries=cache_total,
            cache_by_task=cache_by_task,
            usage_today=usage,
            last_ingestion_at=last_run,
        )
