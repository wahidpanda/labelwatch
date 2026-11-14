import uuid
from collections.abc import AsyncIterator
from datetime import date

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.config import Settings
from app.db.models import SafetyEvent
from app.db.repositories.drugs import DrugRepository
from app.db.repositories.labels import LabelRepository
from app.ingest.normalize import join_units
from app.judge.service import Judge
from app.main import create_app
from tests.integration.test_judge import BRAND_UNIT, FILLER, FakeJudgeModel, _llm

BRAND_SETID = uuid.UUID("11111111-1111-4111-8111-111111111111")
GOOD_SETID = uuid.UUID("22222222-2222-4222-8222-222222222222")
STALE_SETID = uuid.UUID("33333333-3333-4333-8333-333333333333")


@pytest.fixture
async def seeded(engine: AsyncEngine) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        drug = await DrugRepository(session).upsert("montelukast", "montelukast", is_seed=True)
        labels = LabelRepository(session)
        brand = await labels.upsert_set(
            setid=BRAND_SETID, drug_id=drug.id, title="SINGULAIR", role="brand"
        )
        brand_v = await labels.upsert_version(
            spl_set_id=brand.id,
            version=1,
            published_date=date(2020, 1, 1),
            source_url="x",
            raw_sha256="b" * 64,
        )
        session.add(
            SafetyEvent(
                drug_id=drug.id,
                brand_set_id=brand.id,
                to_version_id=brand_v.id,
                event_date=date(2020, 1, 1),
                section_key="boxed_warning",
                change_type="added",
                severity="boxed",
                claim_text="Boxed warning for neuropsychiatric events was added.",
                claim_hash="h-api",
                brand_unit=BRAND_UNIT,
            )
        )
        for setid, units in ((GOOD_SETID, [*FILLER, BRAND_UNIT]), (STALE_SETID, FILLER)):
            generic = await labels.upsert_set(
                setid=setid, drug_id=drug.id, title=f"MONTELUKAST [{setid.hex[:4]}]", role="generic"
            )
            row = await labels.upsert_version(
                spl_set_id=generic.id,
                version=1,
                published_date=date(2020, 7, 1),
                source_url="x",
                raw_sha256="c" * 64,
            )
            digest = await labels.store_section_text(join_units(units))
            await labels.attach_section(
                version_id=row.id, section_key="boxed_warning", text_hash=digest, loinc=None
            )
        await session.commit()
    await Judge(factory, _llm(factory, FakeJudgeModel())).judge_drug("montelukast")
    yield factory
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "truncate drugs, applications, section_texts, ingestion_runs, llm_cache,"
                " llm_budget restart identity cascade"
            )
        )
        await conn.execute(text("refresh materialized view mv_drug_lag"))


@pytest.fixture
async def api(seeded: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncClient]:
    app = create_app(Settings(_env_file=None, env="test", rate_limit_per_minute=1000))
    app.state.session_factory = seeded
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def test_drug_list_detail_and_kpis(api: AsyncClient) -> None:
    page = (await api.get("/api/v1/drugs", params={"q": "monte"})).json()
    [drug] = page["items"]
    assert drug["events"] == 1
    assert drug["generics"] == 2
    assert drug["stale_generics"] == 1
    assert drug["median_lag_days"] == (date(2020, 7, 1) - date(2020, 1, 1)).days
    assert page["next_cursor"] is None

    detail = await api.get(f"/api/v1/drugs/{drug['id']}")
    assert detail.status_code == 200
    assert (await api.get("/api/v1/drugs", params={"q": "zzz"})).json()["items"] == []


async def test_events_matrix_and_judgements(api: AsyncClient) -> None:
    drug_id = (await api.get("/api/v1/drugs")).json()["items"][0]["id"]
    events = (await api.get(f"/api/v1/drugs/{drug_id}/events")).json()["items"]
    [event] = events
    assert event["counts"] == {
        "propagated": 1,
        "partial": 0,
        "not_propagated": 1,
        "insufficient_evidence": 0,
    }
    assert (await api.get(f"/api/v1/drugs/{drug_id}/events", params={"severity": "minor"})).json()[
        "items"
    ] == []

    matrix = (await api.get(f"/api/v1/drugs/{drug_id}/matrix")).json()
    assert len(matrix["events"]) == 1
    assert {r["generic_set"]["setid"] for r in matrix["rows"]} == {
        str(GOOD_SETID),
        str(STALE_SETID),
    }

    detail = (await api.get(f"/api/v1/events/{event['id']}")).json()
    assert detail["brand_setid"] == str(BRAND_SETID)
    assert detail["brand_unit"] == BRAND_UNIT

    judgements = (await api.get(f"/api/v1/events/{event['id']}/judgements")).json()["items"]
    statuses = {j["generic_set"]["setid"]: j["status"] for j in judgements}
    assert statuses == {str(GOOD_SETID): "propagated", str(STALE_SETID): "not_propagated"}
    good = next(j for j in judgements if j["status"] == "propagated")
    assert good["first_version"] == {"number": 1, "date": "2020-07-01"}
    assert good["evidence"]["quotes"] == [BRAND_UNIT]

    one = await api.get(f"/api/v1/judgements/{good['id']}")
    assert one.json()["id"] == good["id"]


async def test_section_text_stale_csv_overview_methodology(api: AsyncClient) -> None:
    section = await api.get(f"/api/v1/sets/{GOOD_SETID}/versions/1/sections/boxed_warning")
    assert section.status_code == 200
    assert BRAND_UNIT in section.text

    stale = (await api.get("/api/v1/generics/stale")).json()["items"]
    assert [s["generic_set"]["setid"] for s in stale] == [str(STALE_SETID)]
    assert stale[0]["days_since_event"] > 90

    csv = await api.get("/api/v1/generics/stale", headers={"Accept": "text/csv"})
    assert csv.headers["content-type"].startswith("text/csv")
    lines = csv.text.strip().splitlines()
    assert lines[0].startswith("judgement_id,setid")
    assert len(lines) == 2
    via_query = await api.get("/api/v1/generics/stale", params={"format": "csv"})
    assert via_query.text == csv.text

    overview = (await api.get("/api/v1/stats/overview")).json()
    assert overview["events"] == 1
    assert overview["judgements"] == 2
    assert overview["stale_share"] == 0.5

    methodology = (await api.get("/api/v1/methodology")).json()
    assert methodology["prompt_version"] == "v1"
    assert "not medical advice" in methodology["disclaimer"]


@pytest.mark.parametrize(
    "path",
    [
        f"/api/v1/drugs/{uuid.UUID(int=1)}",
        f"/api/v1/drugs/{uuid.UUID(int=1)}/events",
        f"/api/v1/drugs/{uuid.UUID(int=1)}/matrix",
        f"/api/v1/events/{uuid.UUID(int=1)}",
        f"/api/v1/events/{uuid.UUID(int=1)}/judgements",
        f"/api/v1/judgements/{uuid.UUID(int=1)}",
        f"/api/v1/sets/{GOOD_SETID}/versions/9/sections/boxed_warning",
    ],
)
async def test_missing_resources_are_problem_404(api: AsyncClient, path: str) -> None:
    response = await api.get(path)
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["status"] == 404


@pytest.mark.parametrize(
    ("path", "params"),
    [
        ("/api/v1/drugs", {"limit": 0}),
        ("/api/v1/drugs", {"limit": 101}),
        ("/api/v1/drugs", {"cursor": "!!notbase64"}),
        ("/api/v1/drugs/not-a-uuid", {}),
        (f"/api/v1/sets/{GOOD_SETID}/versions/1/sections/bogus", {}),
    ],
)
async def test_bad_input_is_problem_4xx(
    api: AsyncClient, path: str, params: dict[str, str | int]
) -> None:
    response = await api.get(path, params=params)
    assert response.status_code in (400, 422)
    assert response.headers["content-type"] == "application/problem+json"


async def test_pagination_cursor_round_trip(api: AsyncClient) -> None:
    first = (await api.get("/api/v1/drugs", params={"limit": 1})).json()
    assert len(first["items"]) == 1
    assert first["next_cursor"]
    second = (
        await api.get("/api/v1/drugs", params={"limit": 1, "cursor": first["next_cursor"]})
    ).json()
    assert second["items"] == []
