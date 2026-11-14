import uuid
from collections.abc import AsyncIterator
from datetime import date
from typing import Any

import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import Runnable, RunnableLambda
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.db.models import IngestionRun, SafetyEvent
from app.db.repositories.drugs import DrugRepository
from app.db.repositories.labels import LabelRepository
from app.detect.events import EventDetector
from app.ingest.normalize import join_units
from app.llm.factory import ProviderConfig, StructuredLLM, StructuredModel, Task, budget_scope
from app.llm.schemas import ClassifyOut

NEW_WARNING = (
    "Serious neuropsychiatric events, including suicidal thinking, have been reported in "
    "patients taking montelukast."
)
EDITORIAL = "For details of the clinical study design, see the editorial note in section 14."
BASE = [
    "Montelukast is not indicated for the reversal of bronchospasm in acute asthma attacks.",
    "Patients should have appropriate rescue medication available.",
]


class KeywordModel:
    def __init__(self) -> None:
        self.calls = 0

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Runnable[Any, Any]:
        async def run(messages: Any) -> dict[str, Any]:
            self.calls += 1
            after = str(messages[-1].content).split("AFTER: ", 1)[1]
            editorial = "editorial" in after
            parsed = ClassifyOut(
                is_substantive=not editorial,
                change_type="editorial" if editorial else "added",
                severity="major",
                claim=after[:120],
                reason="test",
            )
            return {"raw": AIMessage(content=""), "parsed": parsed, "parsing_error": None}

        return RunnableLambda(run)


@pytest.fixture
async def factory(engine: AsyncEngine) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    yield async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "truncate drugs, applications, section_texts, ingestion_runs, llm_cache,"
                " llm_budget restart identity cascade"
            )
        )


async def _seed(factory: async_sessionmaker[AsyncSession], versions: list[list[str]]) -> None:
    async with factory() as session:
        drug = await DrugRepository(session).upsert("montelukast", "montelukast", is_seed=True)
        labels = LabelRepository(session)
        spl_set = await labels.upsert_set(
            setid=uuid.uuid4(), drug_id=drug.id, title="SINGULAIR [ORGANON LLC]", role="brand"
        )
        for number, units in enumerate(versions, start=1):
            row = await labels.upsert_version(
                spl_set_id=spl_set.id,
                version=number,
                published_date=date(2015 + number, 1, 1),
                source_url="https://dailymed.nlm.nih.gov/x",
                raw_sha256=f"{number:064d}",
            )
            digest = await labels.store_section_text(join_units(units))
            await labels.attach_section(
                version_id=row.id, section_key="warnings_precautions", text_hash=digest, loinc=None
            )
        await session.commit()


def _llm(factory: async_sessionmaker[AsyncSession], model: KeywordModel) -> StructuredLLM:
    def builder(config: ProviderConfig, task: Task) -> StructuredModel:
        return model

    configs = [ProviderConfig("ollama", "fake", daily_cap=1000, rps=100.0)]
    return StructuredLLM("classify", configs, budget_scope(factory), builder=builder)


async def test_events_detected_editorial_dropped_and_rerun_is_free(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    await _seed(
        factory,
        [
            BASE,
            [*BASE, "5.2 Neuropsychiatric Events", NEW_WARNING, EDITORIAL],
            [*BASE, "5.2 Neuropsychiatric Events", NEW_WARNING, EDITORIAL],
        ],
    )
    model = KeywordModel()
    stats = await EventDetector(factory, _llm(factory, model)).detect_drug("Montelukast Sodium")
    assert stats.pairs == 2
    assert stats.sections_changed == 1  # the identical v2 -> v3 section is skipped
    assert stats.trivial == 1  # the heading
    assert stats.editorial == 1
    assert stats.events_created == 1
    assert model.calls == 2

    async with factory() as session:
        events = (await session.scalars(select(SafetyEvent))).all()
    assert len(events) == 1
    assert events[0].brand_unit == NEW_WARNING
    assert events[0].event_date == date(2017, 1, 1)
    assert events[0].classifier is not None
    assert events[0].classifier["prompt_version"] == "v1"

    again = await EventDetector(factory, _llm(factory, model)).detect_drug("montelukast")
    assert model.calls == 2
    assert again.events_created == 0
    assert again.known == 1
    assert again.cache_hits == 1
    async with factory() as session:
        assert len((await session.scalars(select(SafetyEvent))).all()) == 1


async def test_formatting_only_changes_produce_no_candidates(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    reformatted = [u.upper().replace(" ", "  ") for u in BASE]
    await _seed(factory, [BASE, list(reversed(reformatted))])
    model = KeywordModel()
    stats = await EventDetector(factory, _llm(factory, model)).detect_drug("montelukast")
    assert stats.candidates == 0
    assert stats.events_created == 0
    assert model.calls == 0


async def test_call_cap_defers_and_marks_run_partial(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    await _seed(factory, [BASE, [*BASE, NEW_WARNING]])
    model = KeywordModel()
    stats = await EventDetector(factory, _llm(factory, model), max_calls=0).detect_drug(
        "montelukast"
    )
    assert stats.deferred is True
    assert model.calls == 0
    async with factory() as session:
        status = await session.scalar(select(IngestionRun.status))
    assert status == "partial"


async def test_unknown_drug_fails_the_run(factory: async_sessionmaker[AsyncSession]) -> None:
    with pytest.raises(LookupError):
        await EventDetector(factory, _llm(factory, KeywordModel())).detect_drug("nothing")
