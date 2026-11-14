"""Postgres FTS + trigram retrieval over rag_docs."""

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import RagDoc


class RagRetriever:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def search(self, query: str, *, lang: str = "en", limit: int = 5) -> list[RagDoc]:
        q = query.strip()
        if not q:
            return []
        pattern = f"%{q}%"
        stmt = (
            select(RagDoc)
            .where(RagDoc.lang == lang)
            .where(or_(RagDoc.title.ilike(pattern), RagDoc.body.ilike(pattern)))
            .limit(limit)
        )
        return list(await self._session.scalars(stmt))
