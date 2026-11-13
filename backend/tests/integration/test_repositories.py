import uuid
from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.budget import DatabaseSizeExceededError, ensure_database_capacity
from app.db.models import SectionText
from app.db.repositories.budget import BudgetRepository
from app.db.repositories.drugs import DrugRepository
from app.db.repositories.ingestion_runs import IngestionRunRepository
from app.db.repositories.labels import LabelRepository, text_hash

DAY = date(2026, 11, 13)


async def test_drug_upsert_is_idempotent_and_never_clears_values(session: AsyncSession) -> None:
    repo = DrugRepository(session)
    first = await repo.upsert("Warfarin Sodium", "warfarin", is_seed=True, drug_class="anticoag")
    second = await repo.upsert("Warfarin", "warfarin", is_seed=False)
    assert second.id == first.id
    assert second.is_seed is True
    assert second.drug_class == "anticoag"
    assert [d.ingredient_norm for d in await repo.list_seeds()] == ["warfarin"]
    assert await repo.get_by_norm("warfarin") is not None
    assert (await repo.get(first.id)) is not None


async def test_labels_versions_and_section_dedupe(session: AsyncSession) -> None:
    drug = await DrugRepository(session).upsert("Montelukast", "montelukast")
    repo = LabelRepository(session)
    setid = uuid.uuid4()
    spl_set = await repo.upsert_set(setid=setid, drug_id=drug.id, title="Singulair", role="brand")
    again = await repo.upsert_set(
        setid=setid, drug_id=drug.id, title="SINGULAIR tablets", role="brand", labeler="Organon"
    )
    assert again.id == spl_set.id
    assert again.title == "SINGULAIR tablets"
    assert (await repo.get_set_by_setid(setid)) is not None

    v1 = await repo.upsert_version(
        spl_set_id=spl_set.id, version=1, published_date=date(2020, 3, 1), source_url="u1"
    )
    v2 = await repo.upsert_version(
        spl_set_id=spl_set.id, version=2, published_date=date(2021, 3, 1), source_url="u2"
    )
    assert [v.version for v in await repo.list_versions(spl_set.id)] == [1, 2]

    body = "Serious neuropsychiatric events have been reported."
    h1 = await repo.store_section_text(body)
    h2 = await repo.store_section_text(body)
    assert h1 == h2 == text_hash(body)
    for version in (v1, v2):
        await repo.attach_section(
            version_id=version.id, section_key="boxed_warning", text_hash=h1, loinc="34066-1"
        )
    stored = await session.scalar(
        select(func.count()).select_from(SectionText).where(SectionText.hash == h1)
    )
    assert stored == 1
    assert await repo.get_section_text(v2.id, "boxed_warning") == body
    assert await repo.get_section_text(v2.id, "pregnancy") is None


async def test_ingestion_run_lifecycle(session: AsyncSession) -> None:
    repo = IngestionRunRepository(session)
    run_id = await repo.start("seed", {"drug": "warfarin"})
    await repo.finish(run_id, status="done", stats={"sets": 3})
    run = await repo.get(run_id)
    assert run is not None
    assert run.status == "done"
    assert run.stats == {"sets": 3}
    assert run.finished_at is not None


async def test_llm_budget_counters_accumulate(session: AsyncSession) -> None:
    repo = BudgetRepository(session)
    await repo.record_llm_call(DAY, "groq", "m1", tokens_in=100, tokens_out=10)
    await repo.record_llm_call(DAY, "groq", "m1", tokens_in=50, tokens_out=5)
    await repo.record_llm_call(DAY, "groq", "m2", tokens_in=1, tokens_out=1)
    await repo.record_llm_call(DAY, "google_genai", "g", tokens_in=1, tokens_out=1)
    assert await repo.llm_calls(DAY, "groq") == 3
    assert await repo.llm_calls(DAY, "ollama") == 0


async def test_trace_budget_increments_per_month(session: AsyncSession) -> None:
    repo = BudgetRepository(session)
    month = date(2026, 11, 1)
    assert await repo.traces(month) == 0
    assert await repo.increment_traces(month) == 1
    assert await repo.increment_traces(month) == 2
    assert await repo.traces(month) == 2


async def test_database_size_guard_uses_real_size(session: AsyncSession) -> None:
    repo = BudgetRepository(session)
    size = await ensure_database_capacity(repo, limit_mb=100_000)
    assert size > 0
    with pytest.raises(DatabaseSizeExceededError):
        await ensure_database_capacity(repo, limit_mb=1)
