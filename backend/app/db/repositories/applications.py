import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Application


class ApplicationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(
        self,
        *,
        drug_id: uuid.UUID,
        appl_type: str,
        appl_no: str,
        applicant: str | None,
        trade_name: str | None,
        is_rld: bool,
        products: list[dict[str, Any]],
    ) -> Application:
        stmt = insert(Application).values(
            drug_id=drug_id,
            appl_type=appl_type,
            appl_no=appl_no,
            applicant=applicant,
            trade_name=trade_name,
            is_rld=is_rld,
            products=products,
        )
        upsert = stmt.on_conflict_do_update(
            index_elements=[Application.appl_type, Application.appl_no],
            set_={
                "applicant": stmt.excluded.applicant,
                "trade_name": stmt.excluded.trade_name,
                "is_rld": stmt.excluded.is_rld,
                "products": stmt.excluded.products,
            },
        ).returning(Application)
        row = await self._session.scalar(upsert, execution_options={"populate_existing": True})
        assert row is not None  # noqa: S101 - RETURNING always yields a row
        return row

    async def set_reference(
        self,
        application_id: uuid.UUID,
        reference_id: uuid.UUID,
        *,
        method: str,
        confidence: Decimal,
    ) -> None:
        """Record the RLD link unless a human has already set a manual one."""
        await self._session.execute(
            update(Application)
            .where(
                Application.id == application_id,
                or_(Application.link_method.is_(None), Application.link_method != "manual"),
            )
            .values(
                reference_application_id=reference_id,
                link_method=method,
                link_confidence=confidence,
            )
        )

    async def list_for_drug(self, drug_id: uuid.UUID) -> list[Application]:
        result = await self._session.scalars(
            select(Application)
            .where(Application.drug_id == drug_id)
            .order_by(Application.appl_type, Application.appl_no)
        )
        return list(result)
