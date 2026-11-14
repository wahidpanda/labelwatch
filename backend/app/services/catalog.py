"""Public read models (SPEC section 10)."""

import uuid
from datetime import UTC, date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import RowMapping

from app.db.repositories.catalog import CatalogRepository
from app.errors import AppError
from app.llm.prompts import PROMPT_VERSION

Status = Literal["propagated", "partial", "not_propagated", "insufficient_evidence"]


class Page[T: BaseModel](BaseModel):
    items: list[T]
    next_cursor: str | None = None


class DrugSummary(BaseModel):
    id: uuid.UUID
    ingredient: str
    drug_class: str | None
    events: int
    generics: int
    stale_generics: int
    median_lag_days: float | None
    p90_lag_days: float | None
    last_event_date: date | None


class StatusCounts(BaseModel):
    propagated: int = 0
    partial: int = 0
    not_propagated: int = 0
    insufficient_evidence: int = 0


class EventSummary(BaseModel):
    id: uuid.UUID
    drug_id: uuid.UUID
    event_date: date
    section_key: str
    change_type: str
    severity: str
    claim_text: str
    counts: StatusCounts


class EventDetail(BaseModel):
    id: uuid.UUID
    drug_id: uuid.UUID
    ingredient: str
    event_date: date
    section_key: str
    change_type: str
    severity: str
    claim_text: str
    brand_unit: str
    brand_setid: uuid.UUID
    brand_title: str
    brand_version: int
    counts: StatusCounts


class GenericSetRef(BaseModel):
    setid: uuid.UUID
    title: str
    labeler: str | None
    is_repackager: bool


class FirstVersion(BaseModel):
    number: int
    date: date


class JudgementOut(BaseModel):
    id: uuid.UUID
    event_id: uuid.UUID
    generic_set: GenericSetRef
    status: Status
    lag_days: int | None
    first_version: FirstVersion | None
    confidence: float | None
    method: str
    model: str | None
    non_monotonic: bool
    evidence: dict[str, Any]


class MatrixCell(BaseModel):
    judgement_id: uuid.UUID
    status: Status
    lag_days: int | None


class MatrixRow(BaseModel):
    generic_set: GenericSetRef
    cells: dict[str, MatrixCell]


class MatrixEvent(BaseModel):
    id: uuid.UUID
    event_date: date
    section_key: str
    severity: str
    claim_text: str


class DrugMatrix(BaseModel):
    events: list[MatrixEvent]
    rows: list[MatrixRow]


class StaleGeneric(BaseModel):
    judgement_id: uuid.UUID
    generic_set: GenericSetRef
    event_id: uuid.UUID
    event_date: date
    claim_text: str
    days_since_event: int
    latest_version_date: date | None


class Overview(BaseModel):
    drugs: int
    events: int
    judgements: int
    median_lag_days: float | None
    stale_generics: int
    stale_share: float | None
    last_ingestion_at: datetime | None


class Methodology(BaseModel):
    prompt_version: str
    stale_days: int
    limits: list[str]
    disclaimer: str = Field(
        default=(
            "This is research data about label text, not medical advice. Dates are label "
            "publication dates on DailyMed, not the dates companies made changes."
        )
    )


LIMITS = [
    "Dates are DailyMed publication dates, not the dates companies made or submitted changes.",
    "Companies may implement a safety change with different wording.",
    "A generic label may be waiting on FDA review of its update.",
    "Old-format labels use different section structures; some format changes may be "
    "detected as new text.",
    "Repackager labels copy their source and are excluded from counts by default.",
    "When a brand label is no longer listed, repackaged copies of it stand in as brand history.",
]


def _set_ref(row: RowMapping) -> GenericSetRef:
    return GenericSetRef(
        setid=row["setid"],
        title=row["title"],
        labeler=row["labeler"],
        is_repackager=row["is_repackager"],
    )


def _counts(row: RowMapping) -> StatusCounts:
    return StatusCounts(**{k: row[k] for k in StatusCounts.model_fields})


def _judgement(row: RowMapping) -> JudgementOut:
    first = (
        FirstVersion(number=row["first_version_number"], date=row["first_version_date"])
        if row["first_version_number"] is not None
        else None
    )
    return JudgementOut(
        id=row["id"],
        event_id=row["event_id"],
        generic_set=_set_ref(row),
        status=row["status"],
        lag_days=row["lag_days"],
        first_version=first,
        confidence=float(row["confidence"]) if row["confidence"] is not None else None,
        method=row["method"],
        model=row["model"],
        non_monotonic=row["non_monotonic"],
        evidence={**row["evidence"], "section_key": row["section_key"]},
    )


class CatalogService:
    def __init__(self, repo: CatalogRepository, *, stale_days: int) -> None:
        self._repo = repo
        self._stale_days = stale_days

    async def drugs(self, *, q: str | None, limit: int, offset: int) -> list[DrugSummary]:
        rows = await self._repo.drugs(stale_days=self._stale_days, q=q, limit=limit, offset=offset)
        return [DrugSummary.model_validate(dict(r)) for r in rows]

    async def drug(self, drug_id: uuid.UUID) -> DrugSummary:
        rows = await self._repo.drugs(stale_days=self._stale_days, drug_id=drug_id, limit=1)
        if not rows:
            raise AppError(404, f"Drug {drug_id} was not found.", title="Not Found")
        return DrugSummary.model_validate(dict(rows[0]))

    async def events(
        self,
        drug_id: uuid.UUID,
        *,
        severity: str | None,
        section_key: str | None,
        limit: int,
        offset: int,
    ) -> list[EventSummary]:
        await self.drug(drug_id)
        rows = await self._repo.events(
            drug_id=drug_id, severity=severity, section_key=section_key, limit=limit, offset=offset
        )
        return [EventSummary(**{**dict(r), "counts": _counts(r)}) for r in rows]

    async def event(self, event_id: uuid.UUID) -> EventDetail:
        row = await self._repo.event_detail(event_id)
        if row is None:
            raise AppError(404, f"Event {event_id} was not found.", title="Not Found")
        [summary] = await self._repo.events(event_id=event_id, limit=1)
        return EventDetail(**{**dict(row), "counts": _counts(summary)})

    async def event_judgements(
        self,
        event_id: uuid.UUID,
        *,
        status: str | None,
        include_repackagers: bool,
        limit: int,
        offset: int,
    ) -> list[JudgementOut]:
        await self.event(event_id)
        rows = await self._repo.judgements(
            stale_days=self._stale_days,
            event_id=event_id,
            status=status,
            limit=limit,
            offset=offset,
        )
        return [_judgement(r) for r in rows if include_repackagers or not r["is_repackager"]]

    async def judgement(self, judgement_id: uuid.UUID) -> JudgementOut:
        rows = await self._repo.judgements(
            stale_days=self._stale_days, judgement_id=judgement_id, limit=1
        )
        if not rows:
            raise AppError(404, f"Judgement {judgement_id} was not found.", title="Not Found")
        return _judgement(rows[0])

    async def matrix(self, drug_id: uuid.UUID) -> DrugMatrix:
        await self.drug(drug_id)
        events = await self._repo.events(drug_id=drug_id, limit=500)
        rows = await self._repo.judgements(
            stale_days=self._stale_days, drug_id=drug_id, limit=20_000
        )
        by_set: dict[uuid.UUID, MatrixRow] = {}
        for r in rows:
            row = by_set.setdefault(r["setid"], MatrixRow(generic_set=_set_ref(r), cells={}))
            row.cells[str(r["event_id"])] = MatrixCell(
                judgement_id=r["id"], status=r["status"], lag_days=r["lag_days"]
            )
        return DrugMatrix(
            events=[MatrixEvent.model_validate(dict(e)) for e in events],
            rows=sorted(by_set.values(), key=lambda m: m.generic_set.title),
        )

    async def stale(
        self, *, drug_id: uuid.UUID | None, min_days: int | None, limit: int, offset: int
    ) -> list[StaleGeneric]:
        rows = await self._repo.judgements(
            stale_days=max(min_days or 0, self._stale_days),
            drug_id=drug_id,
            stale_only=True,
            limit=limit,
            offset=offset,
        )
        today = datetime.now(UTC).date()
        return [
            StaleGeneric(
                judgement_id=r["id"],
                generic_set=_set_ref(r),
                event_id=r["event_id"],
                event_date=r["event_date"],
                claim_text=r["claim_text"],
                days_since_event=(today - r["event_date"]).days,
                latest_version_date=r["latest_published"],
            )
            for r in rows
        ]

    async def section_text(self, setid: uuid.UUID, version: int, section_key: str) -> str:
        body = await self._repo.section_text(setid, version, section_key)
        if body is None:
            raise AppError(
                404, "That section is not stored for this label version.", title="Not Found"
            )
        return body

    async def overview(self) -> Overview:
        row = await self._repo.overview(self._stale_days)
        judgements = int(row["judgements"])
        return Overview(
            drugs=row["drugs"],
            events=row["events"],
            judgements=judgements,
            median_lag_days=row["median_lag_days"],
            stale_generics=row["stale"],
            stale_share=round(row["stale"] / judgements, 3) if judgements else None,
            last_ingestion_at=row["last_ingestion_at"],
        )

    def methodology(self) -> Methodology:
        return Methodology(
            prompt_version=PROMPT_VERSION, stale_days=self._stale_days, limits=LIMITS
        )
