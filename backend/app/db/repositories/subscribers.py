import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Subscriber, Watchlist


def normalize_email(email: str) -> str:
    return email.strip().lower()


class SubscriberRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_pending(
        self,
        *,
        email: str,
        locale: str,
        frequency: str,
        min_severity: str,
        consent_version: str,
        drug_ids: list[uuid.UUID],
    ) -> Subscriber:
        norm = normalize_email(email)
        existing = await self._session.scalar(
            select(Subscriber).where(Subscriber.email_norm == norm)
        )
        if existing is not None:
            return existing
        row = Subscriber(
            email=email.strip(),
            email_norm=norm,
            locale=locale,
            frequency=frequency,
            min_severity=min_severity,
            consent_version=consent_version,
        )
        self._session.add(row)
        await self._session.flush()
        for drug_id in drug_ids:
            self._session.add(Watchlist(subscriber_id=row.id, drug_id=drug_id))
        await self._session.flush()
        return row

    async def confirm(self, subscriber_id: uuid.UUID) -> Subscriber | None:
        row = await self._session.get(Subscriber, subscriber_id)
        if row is None:
            return None
        row.status = "active"
        row.confirmed_at = datetime.now(UTC)
        await self._session.flush()
        return row

    async def unsubscribe(self, subscriber_id: uuid.UUID) -> None:
        row = await self._session.get(Subscriber, subscriber_id)
        if row is None:
            return
        row.status = "unsubscribed"
        row.unsubscribed_at = datetime.now(UTC)
        await self._session.execute(
            delete(Watchlist).where(Watchlist.subscriber_id == subscriber_id)
        )
