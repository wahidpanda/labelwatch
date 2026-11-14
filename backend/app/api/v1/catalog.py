import csv
import io
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Header, Path, Query
from fastapi.responses import PlainTextResponse, Response

from app.api.pagination import Cursor, Limit, decode_cursor, next_cursor
from app.deps import CatalogServiceDep
from app.services.catalog import (
    DrugMatrix,
    DrugSummary,
    EventDetail,
    EventSummary,
    JudgementOut,
    Methodology,
    Overview,
    Page,
    StaleGeneric,
)

router = APIRouter(tags=["catalog"])

Severity = Literal["boxed", "major", "moderate", "minor"]
SectionKey = Literal[
    "boxed_warning",
    "warnings_precautions",
    "warnings",
    "precautions",
    "adverse_reactions",
    "contraindications",
    "drug_interactions",
    "specific_populations",
    "pregnancy",
]
StatusFilter = Literal["propagated", "partial", "not_propagated", "insufficient_evidence"]


@router.get("/drugs", response_model=Page[DrugSummary])
async def list_drugs(
    service: CatalogServiceDep,
    q: Annotated[str | None, Query(max_length=80)] = None,
    limit: Limit = 25,
    cursor: Cursor = None,
) -> Page[DrugSummary]:
    offset = decode_cursor(cursor)
    items = await service.drugs(q=q, limit=limit, offset=offset)
    return Page(items=items, next_cursor=next_cursor(offset, limit, len(items)))


@router.get("/drugs/{drug_id}", response_model=DrugSummary)
async def get_drug(drug_id: uuid.UUID, service: CatalogServiceDep) -> DrugSummary:
    return await service.drug(drug_id)


@router.get("/drugs/{drug_id}/events", response_model=Page[EventSummary])
async def list_drug_events(
    drug_id: uuid.UUID,
    service: CatalogServiceDep,
    severity: Severity | None = None,
    section_key: SectionKey | None = None,
    limit: Limit = 25,
    cursor: Cursor = None,
) -> Page[EventSummary]:
    offset = decode_cursor(cursor)
    items = await service.events(
        drug_id, severity=severity, section_key=section_key, limit=limit, offset=offset
    )
    return Page(items=items, next_cursor=next_cursor(offset, limit, len(items)))


@router.get("/drugs/{drug_id}/matrix", response_model=DrugMatrix)
async def get_drug_matrix(drug_id: uuid.UUID, service: CatalogServiceDep) -> DrugMatrix:
    return await service.matrix(drug_id)


@router.get("/events/{event_id}", response_model=EventDetail)
async def get_event(event_id: uuid.UUID, service: CatalogServiceDep) -> EventDetail:
    return await service.event(event_id)


@router.get("/events/{event_id}/judgements", response_model=Page[JudgementOut])
async def list_event_judgements(
    event_id: uuid.UUID,
    service: CatalogServiceDep,
    status: StatusFilter | None = None,
    include_repackagers: bool = False,
    limit: Limit = 25,
    cursor: Cursor = None,
) -> Page[JudgementOut]:
    offset = decode_cursor(cursor)
    items = await service.event_judgements(
        event_id,
        status=status,
        include_repackagers=include_repackagers,
        limit=limit,
        offset=offset,
    )
    return Page(items=items, next_cursor=next_cursor(offset, limit, len(items)))


@router.get("/judgements/{judgement_id}", response_model=JudgementOut)
async def get_judgement(judgement_id: uuid.UUID, service: CatalogServiceDep) -> JudgementOut:
    return await service.judgement(judgement_id)


@router.get(
    "/sets/{setid}/versions/{version}/sections/{section_key}",
    response_class=PlainTextResponse,
)
async def get_section_text(
    setid: uuid.UUID,
    version: Annotated[int, Path(ge=1)],
    section_key: SectionKey,
    service: CatalogServiceDep,
) -> PlainTextResponse:
    body = await service.section_text(setid, version, section_key)
    return PlainTextResponse(body, headers={"Cache-Control": "public, max-age=86400"})


STALE_CSV_FIELDS = [
    "judgement_id",
    "setid",
    "title",
    "labeler",
    "event_id",
    "event_date",
    "days_since_event",
    "latest_version_date",
    "claim_text",
]


@router.get("/generics/stale", response_model=Page[StaleGeneric])
async def list_stale_generics(
    service: CatalogServiceDep,
    drug_id: uuid.UUID | None = None,
    min_days: Annotated[int | None, Query(ge=0, le=36500)] = None,
    limit: Limit = 25,
    cursor: Cursor = None,
    format: Literal["json", "csv"] | None = None,
    accept: Annotated[str | None, Header()] = None,
) -> Page[StaleGeneric] | Response:
    offset = decode_cursor(cursor)
    wants_csv = format == "csv" or (format is None and bool(accept and "text/csv" in accept))
    items = await service.stale(
        drug_id=drug_id,
        min_days=min_days,
        limit=5000 if wants_csv else limit,
        offset=0 if wants_csv else offset,
    )
    if wants_csv:
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=STALE_CSV_FIELDS)
        writer.writeheader()
        for item in items:
            writer.writerow(
                {
                    "judgement_id": item.judgement_id,
                    "setid": item.generic_set.setid,
                    "title": item.generic_set.title,
                    "labeler": item.generic_set.labeler,
                    "event_id": item.event_id,
                    "event_date": item.event_date,
                    "days_since_event": item.days_since_event,
                    "latest_version_date": item.latest_version_date,
                    "claim_text": item.claim_text,
                }
            )
        return Response(
            buffer.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="stale_generics.csv"'},
        )
    return Page(items=items, next_cursor=next_cursor(offset, limit, len(items)))


@router.get("/stats/overview", response_model=Overview)
async def get_overview(service: CatalogServiceDep) -> Overview:
    return await service.overview()


@router.get("/methodology", response_model=Methodology)
async def get_methodology(service: CatalogServiceDep) -> Methodology:
    return service.methodology()
