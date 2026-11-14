import uuid
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Drug, SplSet


class DrugRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(
        self,
        ingredient: str,
        ingredient_norm: str,
        *,
        is_seed: bool = False,
        drug_class: str | None = None,
        rxcui: str | None = None,
    ) -> Drug:
        """Insert or update by normalised ingredient. Never clears existing values."""
        stmt = insert(Drug).values(
            ingredient=ingredient,
            ingredient_norm=ingredient_norm,
            is_seed=is_seed,
            drug_class=drug_class,
            rxcui=rxcui,
        )
        upsert = stmt.on_conflict_do_update(
            index_elements=[Drug.ingredient_norm],
            set_={
                "is_seed": or_(Drug.is_seed, stmt.excluded.is_seed),
                "drug_class": func.coalesce(stmt.excluded.drug_class, Drug.drug_class),
                "rxcui": func.coalesce(stmt.excluded.rxcui, Drug.rxcui),
            },
        ).returning(Drug)
        drug = await self._session.scalar(upsert, execution_options={"populate_existing": True})
        assert drug is not None  # noqa: S101 - RETURNING always yields a row
        return drug

    async def get(self, drug_id: uuid.UUID) -> Drug | None:
        return await self._session.get(Drug, drug_id)

    async def get_by_norm(self, ingredient_norm: str) -> Drug | None:
        return await self._session.scalar(
            select(Drug).where(Drug.ingredient_norm == ingredient_norm)
        )

    async def request(self, ingredient: str, ingredient_norm: str) -> tuple[Drug, bool]:
        """Add a user-requested medicine. Returns the row and whether it was created."""
        existing = await self.get_by_norm(ingredient_norm)
        if existing is not None:
            return existing, False
        drug = Drug(
            ingredient=ingredient, ingredient_norm=ingredient_norm, requested_at=datetime.now(UTC)
        )
        self._session.add(drug)
        await self._session.flush()
        await self._session.refresh(drug)
        return drug, True

    async def has_labels(self, drug_id: uuid.UUID) -> bool:
        found = await self._session.scalar(
            select(SplSet.id).where(SplSet.drug_id == drug_id).limit(1)
        )
        return found is not None

    async def all_ingredients(self) -> list[str]:
        result = await self._session.scalars(select(Drug.ingredient_norm).order_by(Drug.created_at))
        return list(result)

    async def list_seeds(self) -> list[Drug]:
        result = await self._session.scalars(
            select(Drug).where(Drug.is_seed.is_(True)).order_by(Drug.ingredient_norm)
        )
        return list(result)
