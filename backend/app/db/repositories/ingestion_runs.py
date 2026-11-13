import uuid
from typing import Any

from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import IngestionRun


class IngestionRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def start(self, kind: str, params: dict[str, Any] | None = None) -> uuid.UUID:
        run = IngestionRun(kind=kind, status="running", params=params)
        self._session.add(run)
        await self._session.flush()
        return run.id

    async def finish(
        self,
        run_id: uuid.UUID,
        *,
        status: str,
        stats: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        await self._session.execute(
            update(IngestionRun)
            .where(IngestionRun.id == run_id)
            .values(status=status, stats=stats, error=error, finished_at=func.now())
        )

    async def get(self, run_id: uuid.UUID) -> IngestionRun | None:
        return await self._session.get(IngestionRun, run_id, populate_existing=True)
