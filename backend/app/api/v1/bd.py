import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.deps import BdServiceDep
from app.services.bd import BdBrandDetail, BdBrandSummary

router = APIRouter(prefix="/bd", tags=["bangladesh"])


@router.get("/brands")
async def search_brands(
    service: BdServiceDep,
    q: Annotated[str, Query(min_length=1, max_length=80)],
) -> list[BdBrandSummary]:
    return await service.search(q)


@router.get("/brands/{brand_id}")
async def get_brand(brand_id: uuid.UUID, service: BdServiceDep) -> BdBrandDetail:
    return await service.get(brand_id)
