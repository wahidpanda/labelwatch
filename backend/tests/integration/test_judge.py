import uuid
from collections.abc import AsyncIterator
from datetime import date
from typing import Any

import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import Runnable, RunnableLambda
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.db.models import PropagationJudgement, SafetyEvent
from app.db.repositories.drugs import DrugRepository
from app.db.repositories.labels import LabelRepository
from app.ingest.normalize import join_units
from app.judge.service import Judge
from app.llm.factory import ProviderConfig, StructuredLLM, StructuredModel, Task, budget_scope
from app.llm.schemas import JudgeOut

BRAND_UNIT = (
    "Serious neuropsychiatric events, including suicidal thinking and behavior, have been "
    "reported in patients taking montelukast."
)
REWORDED = (
    "Neuropsychiatric events such as suicidal thinking and behavior were reported in patients "
    "receiving montelukast sodium tablets."
)
FILLER = [
    "Montelukast is not indicated for the reversal of bronchospasm in acute asthma attacks.",
    "Neuropsychiatric history should be reviewed before prescribing montelukast to patients.",
]


class FakeJudgeModel:
    def __init__(self, *, invent_quote: bool = False) -> None:
        self.calls = 0
        self.invent_quote = invent_quote

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Runnable[Any, Any]:
        async def run(messages: Any) -> dict[str, Any]:
            self.calls += 1
            prompt = str(messages[-1].content)
            units = [
                line.split(": ", 1)[1] for line in prompt.splitlines() if line.startswith("UNIT")
            ]
            hit = next((u for u in units if "suicidal" in u), None)
            if self.invent_quote:
                parsed = JudgeOut(
                    status="propagated",
                    quotes=["A sentence that is not there."],
                    confidence=0.9,
                    rationale="x",
                )
            elif hit:
                parsed = JudgeOut(
                    status="propagated", quotes=[hit], confidence=0.8, rationale="Same meaning."
                )
            else:
                parsed = JudgeOut(
                    status="not_propagated", quotes=[], confidence=0.7, rationale="Absent."
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


async def _seed(
    factory: async_sessionmaker[AsyncSession], generic_versions: list[list[str]]
) -> None:
    async with factory() as session:
        drug = await DrugRepository(session).upsert("montelukast", "montelukast", is_seed=True)
        labels = LabelRepository(session)
        brand = await labels.upsert_set(
            setid=uuid.uuid4(), drug_id=drug.id, title="SINGULAIR", role="brand"
        )
        brand_v = await labels.upsert_version(
            spl_set_id=brand.id,
            version=1,
            published_date=date(2017, 1, 1),
            source_url="x",
            raw_sha256="b" * 64,
        )
        session.add(
            SafetyEvent(
                drug_id=drug.id,
                brand_set_id=brand.id,
                to_version_id=brand_v.id,
                event_date=date(2017, 1, 1),
                section_key="warnings_precautions",
                change_type="added",
                severity="boxed",
                claim_text="Neuropsychiatric events including suicidal thinking were added.",
                claim_hash="h1",
                brand_unit=BRAND_UNIT,
            )
        )
        generic = await labels.upsert_set(
            setid=uuid.uuid4(), drug_id=drug.id, title="MONTELUKAST [MAKER]", role="generic"
        )
        for number, units in enumerate(generic_versions, start=1):
            row = await labels.upsert_version(
                spl_set_id=generic.id,
                version=number,
                published_date=date(2015 + number, 6, 1),
                source_url="x",
                raw_sha256=f"{number:064d}",
            )
            digest = await labels.store_section_text(join_units(units))
            await labels.attach_section(
                version_id=row.id, section_key="warnings_precautions", text_hash=digest, loinc=None
            )
        await session.commit()


def _llm(factory: async_sessionmaker[AsyncSession], model: FakeJudgeModel) -> StructuredLLM:
    def builder(config: ProviderConfig, task: Task) -> StructuredModel:
        return model

    configs = [ProviderConfig("ollama", "fake", daily_cap=1000, rps=100.0)]
    return StructuredLLM("judge", configs, budget_scope(factory), builder=builder)


async def _judgements(factory: async_sessionmaker[AsyncSession]) -> list[PropagationJudgement]:
    async with factory() as session:
        return list((await session.scalars(select(PropagationJudgement))).all())


async def test_first_propagated_version_and_lag(factory: async_sessionmaker[AsyncSession]) -> None:
    # Versions: 2016 (before event), 2017-06, 2018-06 reworded, 2019-06 exact copy.
    await _seed(factory, [FILLER, FILLER, [*FILLER, REWORDED], [*FILLER, BRAND_UNIT]])
    model = FakeJudgeModel()
    stats = await Judge(factory, _llm(factory, model)).judge_drug("montelukast")
    assert stats.errors == []
    [row] = await _judgements(factory)
    assert row.status == "propagated"
    assert row.method == "baseline_exact"  # decided by the latest version
    assert row.first_version_date == date(2018, 6, 1)
    assert row.lag_days == (date(2018, 6, 1) - date(2017, 1, 1)).days
    assert row.non_monotonic is False
    assert row.evidence["quotes"] == [BRAND_UNIT]

    async with factory() as session:
        lag = (
            await session.execute(
                text("select events, propagated, median_lag_days from mv_drug_lag")
            )
        ).one()
    assert lag.events == 1
    assert lag.propagated == 1

    calls = model.calls
    again = await Judge(factory, _llm(factory, model)).judge_drug("montelukast")
    assert again.skipped_current == 1
    assert model.calls == calls
    assert len(await _judgements(factory)) == 1


async def test_absent_claim_is_not_propagated(factory: async_sessionmaker[AsyncSession]) -> None:
    await _seed(factory, [FILLER, FILLER])
    await Judge(factory, _llm(factory, FakeJudgeModel())).judge_drug("montelukast")
    [row] = await _judgements(factory)
    assert row.status == "not_propagated"
    assert row.lag_days is None
    assert row.first_version_id is None


async def test_invented_quotes_are_rejected(factory: async_sessionmaker[AsyncSession]) -> None:
    await _seed(factory, [[*FILLER, REWORDED]])
    stats = await Judge(factory, _llm(factory, FakeJudgeModel(invent_quote=True))).judge_drug(
        "montelukast"
    )
    assert stats.rejected_quotes == 1
    [row] = await _judgements(factory)
    assert row.status == "insufficient_evidence"


async def test_call_cap_defers_without_writing(factory: async_sessionmaker[AsyncSession]) -> None:
    await _seed(factory, [[*FILLER, REWORDED]])
    stats = await Judge(factory, _llm(factory, FakeJudgeModel()), max_calls=0).judge_drug(
        "montelukast"
    )
    assert stats.deferred is True
    assert await _judgements(factory) == []
