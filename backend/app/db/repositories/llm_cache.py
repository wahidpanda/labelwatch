from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LlmCache


class LlmCacheRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, cache_key: str) -> dict[str, Any] | None:
        return await self._session.scalar(
            select(LlmCache.output).where(LlmCache.cache_key == cache_key)
        )

    async def put(
        self,
        cache_key: str,
        *,
        task: str,
        prompt_version: str,
        provider: str,
        model: str,
        output: dict[str, Any],
    ) -> None:
        await self._session.execute(
            insert(LlmCache)
            .values(
                cache_key=cache_key,
                task=task,
                prompt_version=prompt_version,
                provider=provider,
                model=model,
                output=output,
            )
            .on_conflict_do_nothing(index_elements=[LlmCache.cache_key])
        )
