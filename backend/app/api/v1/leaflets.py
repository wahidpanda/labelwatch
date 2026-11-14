import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Literal

from fastapi import APIRouter, UploadFile
from pydantic import BaseModel

from app.api.pagination import Cursor, Limit, decode_cursor, next_cursor
from app.core.budget import BudgetExceededError
from app.deps import LeafletLlmDep, SessionDep
from app.errors import AppError
from app.leaflet.ocr import MAX_UPLOAD_BYTES, extract, sniff_type
from app.leaflet.service import LeafletCheckIn, LeafletCheckOut, LeafletService, LeafletSummary
from app.llm.factory import LlmSchemaError, LlmUnavailableError
from app.services.catalog import Page

router = APIRouter(tags=["leaflets"])


class ExtractOut(BaseModel):
    text: str
    source: Literal["pdf_text", "vision"]
    pages: int
    sha256: str
    language: str
    legible: bool
    unclear_parts: list[str]
    chars: int


@contextmanager
def llm_errors() -> Iterator[None]:
    try:
        yield
    except BudgetExceededError as exc:
        raise AppError(503, "Today's AI limit is used up. Please try again tomorrow.") from exc
    except LlmUnavailableError as exc:
        raise AppError(503, "The AI service is unavailable. Please try again later.") from exc
    except LlmSchemaError as exc:
        raise AppError(502, "The AI answer could not be read. Please try again.") from exc


@router.post("/leaflets/extract", response_model=ExtractOut)
async def extract_leaflet(file: UploadFile, llm: LeafletLlmDep) -> ExtractOut:
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    content_type = sniff_type(data) or (file.content_type or "")
    with llm_errors():
        result = await extract(data, content_type, llm)
    return ExtractOut(
        text=result.text,
        source=result.source,
        pages=result.pages,
        sha256=result.sha256,
        language=result.language,
        legible=result.legible,
        unclear_parts=result.unclear_parts,
        chars=len(result.text),
    )


@router.post("/leaflets", response_model=LeafletCheckOut, status_code=201)
async def check_leaflet(
    payload: LeafletCheckIn, session: SessionDep, llm: LeafletLlmDep
) -> LeafletCheckOut:
    with llm_errors():
        return await LeafletService(session, llm).check(payload)


@router.get("/leaflets", response_model=Page[LeafletSummary])
async def list_leaflets(
    session: SessionDep,
    llm: LeafletLlmDep,
    drug_id: uuid.UUID | None = None,
    limit: Limit = 25,
    cursor: Cursor = None,
) -> Page[LeafletSummary]:
    offset = decode_cursor(cursor)
    items = await LeafletService(session, llm).recent(drug_id=drug_id, limit=limit, offset=offset)
    return Page(items=items, next_cursor=next_cursor(offset, limit, len(items)))


@router.get("/leaflets/{check_id}", response_model=LeafletCheckOut)
async def get_leaflet(
    check_id: uuid.UUID, session: SessionDep, llm: LeafletLlmDep
) -> LeafletCheckOut:
    return await LeafletService(session, llm).get(check_id)
