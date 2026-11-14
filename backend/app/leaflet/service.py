"""Compare a leaflet with the US brand safety changes recorded for its medicine."""

import re
import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field
from rapidfuzz import fuzz
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LeafletCheck, SafetyEvent
from app.db.repositories.drugs import DrugRepository
from app.db.repositories.events import EventRepository
from app.db.repositories.leaflets import LeafletRepository
from app.errors import AppError
from app.ingest.normalize import hash_form
from app.judge.retrieval import EXACT_THRESHOLD, quote_is_verbatim, rank_units
from app.llm.factory import StructuredLLM
from app.llm.prompts import LEAFLET_SYSTEM, PROMPT_VERSION, leaflet_user
from app.llm.schemas import LeafletBatchOut, LeafletItemOut
from app.services.catalog import Status, StatusCounts

BATCH_SIZE = 8
MAX_LEAFLET_CHARS = 30_000
MAX_BRAND_UNIT_CHARS = 600
# Below this text similarity to earlier uploads of the same brand, the leaflet is flagged.
CONSISTENCY_FLOOR = 0.6
_SPLIT = re.compile(r"\n+|(?<=[.!?।])\s+")

Method = Literal["baseline_exact", "llm"]
LeafletSource = Literal["pdf_text", "vision", "typed"]


class LeafletCheckIn(BaseModel):
    drug_id: uuid.UUID
    brand_name: str = Field(min_length=1, max_length=120)
    manufacturer: str | None = Field(default=None, max_length=120)
    registration_no: str | None = Field(default=None, max_length=60)
    country: str = Field(default="BD", pattern=r"^[A-Z]{2}$")
    source: LeafletSource = "typed"
    file_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    text: str = Field(min_length=40, max_length=MAX_LEAFLET_CHARS)


class LeafletResult(BaseModel):
    event_id: uuid.UUID
    event_date: date
    section_key: str
    severity: str
    claim_text: str
    status: Status
    method: Method
    quotes: list[str]
    rationale: str


class Consistency(BaseModel):
    compared: int = 0
    max_similarity: float | None = None
    duplicate_of: uuid.UUID | None = None
    flagged: bool = False


class LeafletSummary(BaseModel):
    id: uuid.UUID
    drug_id: uuid.UUID
    ingredient: str
    country: str
    brand_name: str
    manufacturer: str | None
    registration_no: str | None
    source: LeafletSource
    counts: StatusCounts
    consistency: Consistency
    verified: bool = False
    created_at: datetime


class LeafletCheckOut(LeafletSummary):
    leaflet_text: str
    results: list[LeafletResult]
    provider: str | None
    model: str | None


def split_units(text: str) -> list[str]:
    return [u.strip() for u in _SPLIT.split(text) if len(u.strip()) >= 3]


def consistency_of(
    text: str, file_sha256: str | None, earlier: list[LeafletCheck], duplicate: LeafletCheck | None
) -> Consistency:
    form = hash_form(text)
    scores = [fuzz.token_set_ratio(form, hash_form(e.leaflet_text)) / 100.0 for e in earlier]
    best = round(max(scores), 3) if scores else None
    return Consistency(
        compared=len(scores),
        max_similarity=best,
        duplicate_of=duplicate.id if duplicate and file_sha256 else None,
        flagged=best is not None and best < CONSISTENCY_FLOOR,
    )


class LeafletService:
    def __init__(self, session: AsyncSession, llm: StructuredLLM) -> None:
        self._session = session
        self._llm = llm
        self._repo = LeafletRepository(session)

    async def check(self, payload: LeafletCheckIn) -> LeafletCheckOut:
        drug = await DrugRepository(self._session).get(payload.drug_id)
        if drug is None:
            raise AppError(404, "Medicine not found.")
        events = await EventRepository(self._session).list_for_drug(drug.id)
        if not events:
            raise AppError(
                409,
                f"No US brand safety changes are recorded for {drug.ingredient} yet. "
                "Try again after its labels have been processed.",
            )
        text = payload.text.strip()
        units = split_units(text)
        results, provider, model = await self._judge(events, units, text)
        counts = StatusCounts()
        for r in results:
            setattr(counts, r.status, getattr(counts, r.status) + 1)
        consistency = consistency_of(
            text,
            payload.file_sha256,
            await self._repo.same_brand(drug.id, payload.brand_name),
            await self._repo.by_sha(payload.file_sha256) if payload.file_sha256 else None,
        )
        row = await self._repo.add(
            drug_id=drug.id,
            country=payload.country,
            brand_name=payload.brand_name.strip(),
            manufacturer=(payload.manufacturer or "").strip() or None,
            registration_no=(payload.registration_no or "").strip() or None,
            source=payload.source,
            file_sha256=payload.file_sha256,
            leaflet_text=text,
            results=[r.model_dump(mode="json") for r in results],
            counts=counts.model_dump(),
            consistency=consistency.model_dump(mode="json"),
            prompt_version=PROMPT_VERSION,
            provider=provider,
            model=model,
        )
        await self._session.commit()
        return to_out(row, drug.ingredient)

    async def _judge(
        self, events: list[SafetyEvent], units: list[str], text: str
    ) -> tuple[list[LeafletResult], str | None, str | None]:
        verdicts: dict[uuid.UUID, tuple[Status, Method, list[str], str]] = {}
        pending: list[SafetyEvent] = []
        for event in events:
            top = rank_units(event.brand_unit, units, k=1)
            if top and top[0].exact >= EXACT_THRESHOLD:
                verdicts[event.id] = (
                    "propagated",
                    "baseline_exact",
                    [top[0].text],
                    "The leaflet repeats the US label text almost word for word.",
                )
            else:
                pending.append(event)
        provider = model = None
        for start in range(0, len(pending), BATCH_SIZE):
            batch = pending[start : start + BATCH_SIZE]
            changes = [
                (n, e.claim_text, e.brand_unit[:MAX_BRAND_UNIT_CHARS])
                for n, e in enumerate(batch, start=1)
            ]
            result = await self._llm.invoke(
                LeafletBatchOut,
                LEAFLET_SYSTEM,
                leaflet_user(changes, text),
                metadata={"feature": "leaflet_check"},
            )
            provider, model = result.provider, result.model
            by_number = {item.change: item for item in result.output.items}
            for n, event in enumerate(batch, start=1):
                verdicts[event.id] = _verified(by_number.get(n), units)
        results = [
            LeafletResult(
                event_id=e.id,
                event_date=e.event_date,
                section_key=e.section_key,
                severity=e.severity,
                claim_text=e.claim_text,
                status=verdicts[e.id][0],
                method=verdicts[e.id][1],
                quotes=verdicts[e.id][2],
                rationale=verdicts[e.id][3],
            )
            for e in events
        ]
        return results, provider, model

    async def get(self, check_id: uuid.UUID) -> LeafletCheckOut:
        found = await self._repo.get(check_id)
        if found is None:
            raise AppError(404, "Leaflet check not found.")
        return to_out(*found)

    async def recent(
        self, *, drug_id: uuid.UUID | None, limit: int, offset: int
    ) -> list[LeafletSummary]:
        rows = await self._repo.recent(drug_id=drug_id, limit=limit, offset=offset)
        return [to_summary(row, ingredient) for row, ingredient in rows]


def _verified(
    item: LeafletItemOut | None, units: list[str]
) -> tuple[Status, Method, list[str], str]:
    if item is None:
        return "insufficient_evidence", "llm", [], "The model gave no verdict for this change."
    quotes = [q for q in item.quotes if q.strip()]
    if item.status in ("propagated", "partial") and not (
        quotes and all(quote_is_verbatim(q, units) for q in quotes)
    ):
        return (
            "insufficient_evidence",
            "llm",
            [],
            "The quoted text was not found word for word in the leaflet.",
        )
    return item.status, "llm", quotes, item.rationale


def to_summary(row: LeafletCheck, ingredient: str) -> LeafletSummary:
    return LeafletSummary(
        id=row.id,
        drug_id=row.drug_id,
        ingredient=ingredient,
        country=row.country,
        brand_name=row.brand_name,
        manufacturer=row.manufacturer,
        registration_no=row.registration_no,
        source=_source(row.source),
        counts=StatusCounts(**row.counts),
        consistency=Consistency(**row.consistency),
        created_at=row.created_at,
    )


def to_out(row: LeafletCheck, ingredient: str) -> LeafletCheckOut:
    summary = to_summary(row, ingredient)
    results: list[dict[str, Any]] = row.results
    return LeafletCheckOut(
        **summary.model_dump(),
        leaflet_text=row.leaflet_text,
        results=[LeafletResult(**r) for r in results],
        provider=row.provider,
        model=row.model,
    )


def _source(value: str) -> LeafletSource:
    if value == "pdf_text":
        return "pdf_text"
    if value == "vision":
        return "vision"
    return "typed"
