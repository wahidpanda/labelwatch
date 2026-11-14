import uuid
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SafetyEvent


class EventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def claim_hashes_for_drug(self, drug_id: uuid.UUID) -> set[str]:
        result = await self._session.scalars(
            select(SafetyEvent.claim_hash).where(SafetyEvent.drug_id == drug_id)
        )
        return set(result)

    async def create(
        self,
        *,
        drug_id: uuid.UUID,
        brand_set_id: uuid.UUID,
        from_version_id: uuid.UUID | None,
        to_version_id: uuid.UUID,
        event_date: date,
        section_key: str,
        change_type: str,
        severity: str,
        claim_text: str,
        claim_hash: str,
        brand_unit: str,
        classifier: dict[str, Any],
    ) -> uuid.UUID | None:
        """Insert one event. Returns None when the claim is already recorded for this set."""
        return await self._session.scalar(
            insert(SafetyEvent)
            .values(
                drug_id=drug_id,
                brand_set_id=brand_set_id,
                from_version_id=from_version_id,
                to_version_id=to_version_id,
                event_date=event_date,
                section_key=section_key,
                change_type=change_type,
                severity=severity,
                claim_text=claim_text,
                claim_hash=claim_hash,
                brand_unit=brand_unit,
                classifier=classifier,
            )
            .on_conflict_do_nothing(
                index_elements=[SafetyEvent.brand_set_id, SafetyEvent.claim_hash]
            )
            .returning(SafetyEvent.id)
        )

    async def list_for_drug(self, drug_id: uuid.UUID) -> list[SafetyEvent]:
        result = await self._session.scalars(
            select(SafetyEvent)
            .where(SafetyEvent.drug_id == drug_id)
            .order_by(SafetyEvent.event_date, SafetyEvent.section_key)
        )
        return list(result)
