import uuid

from pydantic import BaseModel

from app.db.models import BdBrand
from app.db.repositories.bd_brands import BdBrandRepository
from app.errors import AppError


class BdBrandSummary(BaseModel):
    id: uuid.UUID
    brand_name: str
    generic_name: str
    generic_norm: str
    drug_id: uuid.UUID | None
    strength: str | None
    dosage_form: str | None
    manufacturer: str | None
    has_us_label_data: bool


class BdBrandDetail(BdBrandSummary):
    reference_notice: str = (
        "Reference: US FDA labeling on DailyMed, not DGDA labeling. Not medical advice."
    )


class BdService:
    def __init__(self, repo: BdBrandRepository) -> None:
        self._repo = repo

    async def search(self, query: str) -> list[BdBrandSummary]:
        return [_summary(b) for b in await self._repo.search(query)]

    async def get(self, brand_id: uuid.UUID) -> BdBrandDetail:
        row = await self._repo.get(brand_id)
        if row is None:
            raise AppError(404, "Brand not found.")
        return BdBrandDetail(**_summary(row).model_dump())


def _summary(b: BdBrand) -> BdBrandSummary:
    return BdBrandSummary(
        id=b.id,
        brand_name=b.brand_name,
        generic_name=b.generic_name,
        generic_norm=b.generic_norm,
        drug_id=b.drug_id,
        strength=b.strength,
        dosage_form=b.dosage_form,
        manufacturer=b.manufacturer,
        has_us_label_data=b.drug_id is not None,
    )
