"""Ingestion for one drug: Orange Book applications -> DailyMed sets -> versions -> sections."""

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.budget import ensure_database_capacity
from app.db.repositories.applications import ApplicationRepository
from app.db.repositories.budget import BudgetRepository
from app.db.repositories.drugs import DrugRepository
from app.db.repositories.ingestion_runs import IngestionRunRepository
from app.db.repositories.labels import LabelRepository
from app.ingest.dailymed import (
    DailyMedFormatError,
    FetchedVersion,
    SetSummary,
    VersionInfo,
    version_zip_url,
)
from app.ingest.http import UpstreamError
from app.ingest.linker import (
    ApplicationGroup,
    assign_role,
    group_applications,
    is_likely_repackager,
    link_generics,
)
from app.ingest.normalize import normalize_ingredient
from app.ingest.orange_book import OrangeBookProduct
from app.logging import get_logger

log = get_logger(__name__)

BRAND_HISTORY_START = date(2012, 1, 1)


class IngestMode(StrEnum):
    METADATA = "metadata"  # sets and version lists only
    VERSIONS = "versions"  # plus section text for brand and non-repackager generic versions
    FULL = "full"  # plus section text for every set, including repackagers


class LabelSource(Protocol):
    async def list_sets(
        self, *, application_number: str | None = None, drug_name: str | None = None
    ) -> list[SetSummary]: ...

    async def history(self, setid: uuid.UUID) -> list[VersionInfo]: ...

    async def fetch_version(self, setid: uuid.UUID, version: int) -> FetchedVersion: ...


@dataclass
class IngestStats:
    applications: int = 0
    sets: int = 0
    versions: int = 0
    downloaded: int = 0
    sections_attached: int = 0
    skipped_existing: int = 0
    brand_proxy: bool = False
    errors: list[str] = field(default_factory=list)

    def as_json(self) -> dict[str, Any]:
        return {
            "brand_proxy": self.brand_proxy,
            "applications": self.applications,
            "sets": self.sets,
            "versions": self.versions,
            "downloaded": self.downloaded,
            "sections_attached": self.sections_attached,
            "skipped_existing": self.skipped_existing,
            "errors": self.errors[:50],
            "error_count": len(self.errors),
        }


@dataclass
class StoredSet:
    setid: uuid.UUID
    spl_set_id: uuid.UUID
    role: str
    is_repackager: bool
    versions: dict[int, tuple[uuid.UUID, date]]
    done: set[uuid.UUID]


def needs_sections(role: str, is_repackager: bool, published: date, mode: IngestMode) -> bool:
    if mode is IngestMode.METADATA:
        return False
    if mode is IngestMode.FULL:
        return True
    if is_repackager:
        return False
    if role == "brand":
        return published >= BRAND_HISTORY_START
    return role == "generic"


def _ordered(groups: dict[str, ApplicationGroup]) -> list[ApplicationGroup]:
    # Brand applications first so a set listed under several applications keeps the brand one.
    return sorted(groups.values(), key=lambda g: (not g.is_rld, g.appl_type, g.appl_no))


class IngestPipeline:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        source: LabelSource,
        *,
        db_size_limit_mb: int,
    ) -> None:
        self._sessions = session_factory
        self._source = source
        self._db_size_limit_mb = db_size_limit_mb

    async def ingest_drug(
        self,
        ingredient: str,
        products: Sequence[OrangeBookProduct],
        mode: IngestMode = IngestMode.VERSIONS,
    ) -> IngestStats:
        norm = normalize_ingredient(ingredient)
        stats = IngestStats()
        async with self._sessions() as session:
            run_id = await IngestionRunRepository(session).start(
                "ingest_drug", {"ingredient": norm, "mode": mode.value}
            )
            await session.commit()
        status, error = "done", None
        try:
            await self._ingest(
                norm, [p for p in products if p.ingredient_norm == norm], mode, stats
            )
        except Exception as exc:
            status, error = "failed", f"{type(exc).__name__}: {exc}"
            raise
        finally:
            if stats.errors and status == "done":
                status = "partial"
            async with self._sessions() as session:
                await IngestionRunRepository(session).finish(
                    run_id, status=status, stats=stats.as_json(), error=error
                )
                await session.commit()
            log.info("ingest_drug_done", ingredient=norm, status=status, **stats.as_json())
        return stats

    async def _ingest(
        self,
        norm: str,
        products: list[OrangeBookProduct],
        mode: IngestMode,
        stats: IngestStats,
    ) -> None:
        groups = group_applications(products)
        links = link_generics(groups)
        async with self._sessions() as session:
            drug = await DrugRepository(session).upsert(norm, norm, is_seed=True)
            apps = ApplicationRepository(session)
            app_ids: dict[str, uuid.UUID] = {}
            for number, group in groups.items():
                row = await apps.upsert(
                    drug_id=drug.id,
                    appl_type=group.appl_type,
                    appl_no=group.appl_no,
                    applicant=group.applicant_full_name or group.applicant,
                    trade_name=group.trade_name,
                    is_rld=group.is_rld,
                    products=[p.as_json() for p in group.products],
                )
                app_ids[number] = row.id
            for number, link in links.items():
                if link.reference in app_ids:
                    await apps.set_reference(
                        app_ids[number],
                        app_ids[link.reference],
                        method=link.method,
                        confidence=link.confidence,
                    )
            await session.commit()
            drug_id = drug.id
        stats.applications = len(groups)

        seen: set[uuid.UUID] = set()
        brand_sets: list[StoredSet] = []
        for group in _ordered(groups):
            try:
                summaries = await self._source.list_sets(
                    application_number=group.application_number
                )
            except (UpstreamError, DailyMedFormatError) as exc:
                stats.errors.append(f"list_sets {group.application_number}: {exc}")
                continue
            for summary in summaries:
                if summary.setid in seen:
                    continue
                seen.add(summary.setid)
                try:
                    stored = await self._ingest_set(
                        drug_id, app_ids[group.application_number], group, summary, mode, stats
                    )
                except (UpstreamError, DailyMedFormatError) as exc:
                    stats.errors.append(f"set {summary.setid}: {exc}")
                    continue
                if stored.role == "brand":
                    brand_sets.append(stored)

        if mode is not IngestMode.METADATA:
            await self._download_brand_history(brand_sets, stats)

    async def _download_brand_history(
        self, brand_sets: list[StoredSet], stats: IngestStats
    ) -> None:
        """Repackaged brand copies stand in for brand history the active brand set lacks."""
        active_dates = [
            published
            for s in brand_sets
            if not s.is_repackager
            for _vid, published in s.versions.values()
        ]
        start = min(active_dates, default=date.max)
        for stored in brand_sets:
            if not stored.is_repackager:
                continue
            if any(published < start for _vid, published in stored.versions.values()):
                stats.brand_proxy = True
            try:
                await self._download(stored, lambda published: published < start, stats)
            except (UpstreamError, DailyMedFormatError) as exc:
                stats.errors.append(f"set {stored.setid}: {exc}")

    async def _ingest_set(
        self,
        drug_id: uuid.UUID,
        application_id: uuid.UUID,
        group: ApplicationGroup,
        summary: SetSummary,
        mode: IngestMode,
        stats: IngestStats,
    ) -> "StoredSet":
        role = assign_role(group, summary.title)
        repackager = is_likely_repackager(summary.labeler, group)
        history = await self._source.history(summary.setid)
        async with self._sessions() as session:
            labels = LabelRepository(session)
            spl_set = await labels.upsert_set(
                setid=summary.setid,
                drug_id=drug_id,
                title=summary.title,
                role=role,
                labeler=summary.labeler,
                application_id=application_id,
                is_repackager=repackager,
            )
            versions = {}
            for info in history:
                row = await labels.upsert_version(
                    spl_set_id=spl_set.id,
                    version=info.version,
                    published_date=info.published_date,
                    source_url=version_zip_url(summary.setid, info.version),
                )
                versions[info.version] = (row.id, info.published_date)
            if history:
                latest = history[-1]
                await labels.mark_checked(
                    spl_set.id,
                    latest_version=latest.version,
                    latest_published=latest.published_date,
                )
            done = await labels.parsed_version_ids(spl_set.id)
            await session.commit()
            spl_set_id = spl_set.id
        stats.sets += 1
        stats.versions += len(versions)
        stored = StoredSet(summary.setid, spl_set_id, role, repackager, versions, done)
        await self._download(
            stored, lambda published: needs_sections(role, repackager, published, mode), stats
        )
        return stored

    async def _download(
        self, stored: "StoredSet", wanted: Callable[[date], bool], stats: IngestStats
    ) -> None:
        for number, (version_id, published) in sorted(stored.versions.items()):
            if not wanted(published):
                continue
            if version_id in stored.done:
                stats.skipped_existing += 1
                continue
            await self._store_version(
                stored.setid, stored.spl_set_id, number, version_id, published, stats
            )
            stored.done.add(version_id)

    async def _store_version(
        self,
        setid: uuid.UUID,
        spl_set_id: uuid.UUID,
        number: int,
        version_id: uuid.UUID,
        published: date,
        stats: IngestStats,
    ) -> None:
        async with self._sessions() as session:
            await ensure_database_capacity(BudgetRepository(session), self._db_size_limit_mb)
        fetched = await self._source.fetch_version(setid, number)
        if fetched.parsed.version not in (None, number):
            log.warning(
                "spl_version_mismatch", setid=str(setid), asked=number, got=fetched.parsed.version
            )
        async with self._sessions() as session:
            labels = LabelRepository(session)
            for section in fetched.parsed.sections.values():
                digest = await labels.store_section_text(section.body)
                await labels.attach_section(
                    version_id=version_id,
                    section_key=section.key,
                    text_hash=digest,
                    loinc=section.loinc,
                )
                stats.sections_attached += 1
            await labels.upsert_version(
                spl_set_id=spl_set_id,
                version=number,
                published_date=published,
                source_url=fetched.source_url,
                raw_sha256=fetched.zip_sha256,
            )
            await session.commit()
        stats.downloaded += 1
