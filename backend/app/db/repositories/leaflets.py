import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Drug, LeafletCheck


class LeafletRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, **values: Any) -> LeafletCheck:
        row = LeafletCheck(**values)
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def get(self, check_id: uuid.UUID) -> tuple[LeafletCheck, str] | None:
        row = (
            await self._session.execute(
                select(LeafletCheck, Drug.ingredient)
                .join(Drug, Drug.id == LeafletCheck.drug_id)
                .where(LeafletCheck.id == check_id)
            )
        ).first()
        return (row[0], row[1]) if row else None

    async def recent(
        self, *, drug_id: uuid.UUID | None, limit: int, offset: int
    ) -> list[tuple[LeafletCheck, str]]:
        stmt = select(LeafletCheck, Drug.ingredient).join(Drug, Drug.id == LeafletCheck.drug_id)
        if drug_id is not None:
            stmt = stmt.where(LeafletCheck.drug_id == drug_id)
        rows = await self._session.execute(
            stmt.order_by(LeafletCheck.created_at.desc()).limit(limit).offset(offset)
        )
        return [(r[0], r[1]) for r in rows]

    async def same_brand(self, drug_id: uuid.UUID, brand_name: str) -> list[LeafletCheck]:
        result = await self._session.scalars(
            select(LeafletCheck)
            .where(
                LeafletCheck.drug_id == drug_id,
                func.lower(LeafletCheck.brand_name) == brand_name.lower(),
            )
            .order_by(LeafletCheck.created_at.desc())
            .limit(20)
        )
        return list(result)

    async def by_sha(self, sha256: str) -> LeafletCheck | None:
        return await self._session.scalar(
            select(LeafletCheck).where(LeafletCheck.file_sha256 == sha256).limit(1)
        )
