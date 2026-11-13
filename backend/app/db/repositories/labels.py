import hashlib
import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SectionText, SplSet, SplVersion, VersionSection


def text_hash(normalised_text: str) -> str:
    return hashlib.sha256(normalised_text.encode("utf-8")).hexdigest()


class LabelRepository:
    """SPL sets, their versions, and hash-deduplicated safety section text."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_set(
        self,
        *,
        setid: uuid.UUID,
        drug_id: uuid.UUID,
        title: str,
        role: str,
        labeler: str | None = None,
        application_id: uuid.UUID | None = None,
        is_repackager: bool = False,
    ) -> SplSet:
        stmt = insert(SplSet).values(
            setid=setid,
            drug_id=drug_id,
            title=title,
            role=role,
            labeler=labeler,
            application_id=application_id,
            is_repackager=is_repackager,
        )
        upsert = stmt.on_conflict_do_update(
            index_elements=[SplSet.setid],
            set_={
                "title": stmt.excluded.title,
                "role": stmt.excluded.role,
                "labeler": stmt.excluded.labeler,
                "application_id": stmt.excluded.application_id,
                "is_repackager": stmt.excluded.is_repackager,
            },
        ).returning(SplSet)
        spl_set = await self._session.scalar(upsert, execution_options={"populate_existing": True})
        assert spl_set is not None  # noqa: S101 - RETURNING always yields a row
        return spl_set

    async def get_set_by_setid(self, setid: uuid.UUID) -> SplSet | None:
        return await self._session.scalar(select(SplSet).where(SplSet.setid == setid))

    async def upsert_version(
        self,
        *,
        spl_set_id: uuid.UUID,
        version: int,
        published_date: date,
        source_url: str,
        raw_sha256: str | None = None,
    ) -> SplVersion:
        stmt = insert(SplVersion).values(
            spl_set_id=spl_set_id,
            version=version,
            published_date=published_date,
            source_url=source_url,
            raw_sha256=raw_sha256,
        )
        upsert = stmt.on_conflict_do_update(
            index_elements=[SplVersion.spl_set_id, SplVersion.version],
            set_={
                "published_date": stmt.excluded.published_date,
                "source_url": stmt.excluded.source_url,
                "raw_sha256": stmt.excluded.raw_sha256,
            },
        ).returning(SplVersion)
        row = await self._session.scalar(upsert, execution_options={"populate_existing": True})
        assert row is not None  # noqa: S101 - RETURNING always yields a row
        return row

    async def list_versions(self, spl_set_id: uuid.UUID) -> list[SplVersion]:
        result = await self._session.scalars(
            select(SplVersion)
            .where(SplVersion.spl_set_id == spl_set_id)
            .order_by(SplVersion.version)
        )
        return list(result)

    async def store_section_text(self, body: str) -> str:
        """Store normalised section text once per distinct content. Returns its hash."""
        digest = text_hash(body)
        await self._session.execute(
            insert(SectionText)
            .values(hash=digest, body=body, char_len=len(body))
            .on_conflict_do_nothing(index_elements=[SectionText.hash])
        )
        return digest

    async def attach_section(
        self, *, version_id: uuid.UUID, section_key: str, text_hash: str, loinc: str | None
    ) -> None:
        stmt = insert(VersionSection).values(
            version_id=version_id, section_key=section_key, text_hash=text_hash, loinc=loinc
        )
        await self._session.execute(
            stmt.on_conflict_do_update(
                index_elements=[VersionSection.version_id, VersionSection.section_key],
                set_={"text_hash": stmt.excluded.text_hash, "loinc": stmt.excluded.loinc},
            )
        )

    async def get_section_text(self, version_id: uuid.UUID, section_key: str) -> str | None:
        return await self._session.scalar(
            select(SectionText.body)
            .join(VersionSection, VersionSection.text_hash == SectionText.hash)
            .where(
                VersionSection.version_id == version_id,
                VersionSection.section_key == section_key,
            )
        )
