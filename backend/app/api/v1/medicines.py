import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel, Field

from app.db.repositories.drugs import DrugRepository
from app.deps import OpenFdaDep, SessionDep
from app.errors import AppError
from app.ingest.normalize import normalize_ingredient
from app.ingest.openfda import OpenFdaError, clean_query

router = APIRouter(tags=["medicines"])


class MedicineSuggestion(BaseModel):
    name: str
    applications: int
    drug_id: uuid.UUID | None = None


class MedicineIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)


class MedicineOut(BaseModel):
    drug_id: uuid.UUID
    ingredient: str
    created: bool
    has_labels: bool


@router.get("/medicines/search", response_model=list[MedicineSuggestion])
async def search_medicines(
    q: Annotated[str, Query(min_length=2, max_length=60)],
    session: SessionDep,
    fda: OpenFdaDep,
) -> list[MedicineSuggestion]:
    try:
        names = await fda.search(q)
    except OpenFdaError as exc:
        raise AppError(503, "The FDA medicine search is unavailable right now.") from exc
    drugs = DrugRepository(session)
    out = []
    for item in names:
        existing = await drugs.get_by_norm(normalize_ingredient(item.name))
        out.append(
            MedicineSuggestion(
                name=item.name,
                applications=item.applications,
                drug_id=existing.id if existing else None,
            )
        )
    return out


@router.post("/medicines", response_model=MedicineOut, status_code=201)
async def add_medicine(
    payload: MedicineIn, response: Response, session: SessionDep, fda: OpenFdaDep
) -> MedicineOut:
    name = clean_query(payload.name)
    ingredient = normalize_ingredient(name)
    if not ingredient:
        raise AppError(422, "Enter a medicine's generic name, for example montelukast.")
    drugs = DrugRepository(session)
    existing = await drugs.get_by_norm(ingredient)
    if existing is None:
        try:
            known = await fda.exists(name)
        except OpenFdaError as exc:
            raise AppError(503, "The FDA medicine check is unavailable right now.") from exc
        if not known:
            raise AppError(
                404, f"'{payload.name}' was not found in FDA drug data. Use the generic name."
            )
    drug, created = await drugs.request(ingredient, ingredient)
    await session.commit()
    if not created:
        response.status_code = 200
    return MedicineOut(
        drug_id=drug.id,
        ingredient=drug.ingredient,
        created=created,
        has_labels=await drugs.has_labels(drug.id),
    )
