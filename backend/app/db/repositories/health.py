from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class HealthRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def ping(self) -> None:
        await self._session.execute(text("select 1"))

    async def schema_version(self) -> str | None:
        exists = await self._session.scalar(text("select to_regclass('public.schema_migrations')"))
        if exists is None:
            return None
        version = await self._session.scalar(text("select max(version) from schema_migrations"))
        return None if version is None else str(version)
