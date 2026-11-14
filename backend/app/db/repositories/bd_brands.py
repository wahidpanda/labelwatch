import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BdBrand


class BdBrandRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def search(self, query: str, limit: int = 10) -> list[BdBrand]:
        norm = query.strip().lower()
        if not norm:
            return []
        pfx = f"{norm}%"
        stmt = (
            select(BdBrand)
            .where(
                or_(
                    func.similarity(BdBrand.brand_norm, norm) > 0.25,
                    BdBrand.brand_norm.like(pfx),
                    BdBrand.generic_norm.like(pfx),
                )
            )
            .order_by(func.similarity(BdBrand.brand_norm, norm).desc().nulls_last())
            .limit(limit)
        )
        return list(await self._session.scalars(stmt))

    async def get(self, brand_id: uuid.UUID) -> BdBrand | None:
        return await self._session.get(BdBrand, brand_id)
