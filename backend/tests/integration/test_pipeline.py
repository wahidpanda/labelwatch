import uuid
from collections.abc import AsyncIterator
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.db.models import IngestionRun, SectionText, SplSet, SplVersion, VersionSection
from app.ingest.dailymed import FetchedVersion, SetSummary, VersionInfo
from app.ingest.http import UpstreamError
from app.ingest.orange_book import OrangeBookProduct, parse_products
from app.ingest.pipeline import IngestMode, IngestPipeline
from app.ingest.spl_parser import parse_spl

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
BRAND = uuid.UUID("482dcc92-b47f-4ea6-854a-f5ac2aea7842")
REPACK = uuid.UUID("6ffff72c-8784-477b-8722-5434a19881a0")
GENERIC = uuid.UUID("ba42b0a9-83f1-4283-a853-f99cdd0761b9")


class FakeDailyMed:
    def __init__(self, generic_anda: str, generic_labeler: str) -> None:
        self.generic_anda = generic_anda
        self.generic_labeler = generic_labeler
        self.fetches: list[tuple[uuid.UUID, int]] = []
        self.fail_version: tuple[uuid.UUID, int] | None = None
        self.brand_active = True

    async def list_sets(
        self, *, application_number: str | None = None, drug_name: str | None = None
    ) -> list[SetSummary]:
        if application_number == "NDA020829":
            brand = SetSummary(
                BRAND, "SINGULAIR (MONTELUKAST SODIUM) TABLET [ORGANON LLC]", 2, date(2025, 6, 25)
            )
            repack = SetSummary(
                REPACK, "SINGULAIR TABLET [PD-RX PHARMACEUTICALS, INC.]", 1, date(2024, 1, 1)
            )
            return [brand, repack] if self.brand_active else [repack]
        if application_number == "NDA020830" and self.brand_active:
            # The brand set is listed again under its second NDA; it must not be duplicated.
            return [SetSummary(BRAND, "SINGULAIR [ORGANON LLC]", 2, date(2025, 6, 25))]
        if application_number == self.generic_anda:
            title = f"MONTELUKAST SODIUM TABLET [{self.generic_labeler}]"
            return [SetSummary(GENERIC, title, 2, date(2026, 1, 1))]
        return []

    async def history(self, setid: uuid.UUID) -> list[VersionInfo]:
        if setid == BRAND:
            return [
                VersionInfo(1, date(2011, 6, 1)),
                VersionInfo(2, date(2020, 3, 1)),
                VersionInfo(3, date(2025, 6, 25)),
            ]
        if setid == REPACK:
            return [VersionInfo(1, date(2024, 1, 1))]
        return [VersionInfo(1, date(2021, 1, 1)), VersionInfo(2, date(2026, 1, 1))]

    async def fetch_version(self, setid: uuid.UUID, version: int) -> FetchedVersion:
        if (setid, version) == self.fail_version:
            raise UpstreamError("https://dailymed.nlm.nih.gov/x", 503, "Upstream request failed")
        self.fetches.append((setid, version))
        name = "singulair_old_format_2010.xml" if version == 1 else "singulair_plr_v5.xml"
        with (FIXTURES / "spl" / name).open("rb") as handle:
            parsed = parse_spl(handle)
        parsed.version = version
        return FetchedVersion(
            parsed=parsed,
            source_url=f"https://dailymed.nlm.nih.gov/{setid}/{version}",
            zip_sha256="ab" * 32,
        )


@pytest.fixture
async def factory(engine: AsyncEngine) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    yield async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "truncate drugs, applications, section_texts, ingestion_runs restart identity cascade"
            )
        )


def _montelukast_products() -> list[OrangeBookProduct]:
    with (FIXTURES / "orange_book_products_sample.txt").open(encoding="utf-8") as handle:
        return list(parse_products(handle, {"montelukast"}))


async def _count(factory: async_sessionmaker[AsyncSession], model: type) -> int:
    async with factory() as session:
        return int(await session.scalar(select(func.count()).select_from(model)) or 0)


async def test_ingest_is_complete_and_idempotent(factory: async_sessionmaker[AsyncSession]) -> None:
    products = _montelukast_products()
    generic = next(p for p in products if p.appl_type == "ANDA")
    source = FakeDailyMed(
        generic.application_number, generic.applicant_full_name or generic.applicant
    )
    pipeline = IngestPipeline(factory, source, db_size_limit_mb=100_000)

    stats = await pipeline.ingest_drug("Montelukast Sodium", products, IngestMode.VERSIONS)
    assert stats.errors == []
    assert stats.sets == 3
    # Brand: versions since 2012 only (2 and 3). Generic: all versions. Repackager: none.
    assert sorted(source.fetches) == sorted([(BRAND, 2), (BRAND, 3), (GENERIC, 1), (GENERIC, 2)])

    async with factory() as session:
        roles = dict((await session.execute(select(SplSet.setid, SplSet.role))).all())
        repack = await session.scalar(select(SplSet.is_repackager).where(SplSet.setid == REPACK))
        brand_latest = await session.scalar(
            select(SplSet.latest_version).where(SplSet.setid == BRAND)
        )
    assert roles == {BRAND: "brand", REPACK: "brand", GENERIC: "generic"}
    assert repack is True
    assert brand_latest == 3

    counts = {
        m.__name__: await _count(factory, m)
        for m in (SplSet, SplVersion, VersionSection, SectionText)
    }
    # Identical section text across versions is stored once.
    assert counts["SectionText"] < counts["VersionSection"]

    source.fetches.clear()
    again = await pipeline.ingest_drug("montelukast", products, IngestMode.VERSIONS)
    assert source.fetches == []
    assert again.downloaded == 0
    assert again.skipped_existing == 4
    assert {
        m.__name__: await _count(factory, m)
        for m in (SplSet, SplVersion, VersionSection, SectionText)
    } == counts

    async with factory() as session:
        runs = (await session.scalars(select(IngestionRun).order_by(IngestionRun.started_at))).all()
    assert [r.status for r in runs] == ["done", "done"]
    assert runs[0].stats is not None
    assert runs[0].stats["downloaded"] == 4


async def test_failed_download_is_recorded_and_retried_next_run(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    products = _montelukast_products()
    generic = next(p for p in products if p.appl_type == "ANDA")
    source = FakeDailyMed(
        generic.application_number, generic.applicant_full_name or generic.applicant
    )
    source.fail_version = (GENERIC, 2)
    pipeline = IngestPipeline(factory, source, db_size_limit_mb=100_000)

    stats = await pipeline.ingest_drug("montelukast", products, IngestMode.VERSIONS)
    assert len(stats.errors) == 1
    async with factory() as session:
        status = await session.scalar(select(IngestionRun.status))
    assert status == "partial"

    source.fail_version = None
    source.fetches.clear()
    retry = await pipeline.ingest_drug("montelukast", products, IngestMode.VERSIONS)
    assert retry.errors == []
    assert (GENERIC, 2) in source.fetches


async def test_metadata_mode_downloads_nothing_and_size_guard_blocks(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    products = _montelukast_products()
    generic = next(p for p in products if p.appl_type == "ANDA")
    source = FakeDailyMed(
        generic.application_number, generic.applicant_full_name or generic.applicant
    )
    stats = await IngestPipeline(factory, source, db_size_limit_mb=100_000).ingest_drug(
        "montelukast", products, IngestMode.METADATA
    )
    assert source.fetches == []
    assert stats.versions == 6

    from app.core.budget import DatabaseSizeExceededError

    with pytest.raises(DatabaseSizeExceededError):
        await IngestPipeline(factory, source, db_size_limit_mb=1).ingest_drug(
            "montelukast", products, IngestMode.VERSIONS
        )
    async with factory() as session:
        statuses = (
            await session.scalars(select(IngestionRun.status).order_by(IngestionRun.started_at))
        ).all()
    assert statuses[-1] == "failed"


async def test_repackaged_brand_copies_stand_in_when_brand_is_inactive(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    products = _montelukast_products()
    generic = next(p for p in products if p.appl_type == "ANDA")
    source = FakeDailyMed(
        generic.application_number, generic.applicant_full_name or generic.applicant
    )
    source.brand_active = False
    stats = await IngestPipeline(factory, source, db_size_limit_mb=100_000).ingest_drug(
        "montelukast", products, IngestMode.VERSIONS
    )
    assert stats.brand_proxy is True
    assert (REPACK, 1) in source.fetches
