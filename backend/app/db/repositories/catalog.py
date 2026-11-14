"""Read-only queries behind the public API."""

import uuid
from typing import Any

from sqlalchemy import RowMapping, text
from sqlalchemy.ext.asyncio import AsyncSession

_DRUGS = """
select d.id, d.ingredient, d.drug_class,
  coalesce(l.events, 0) as events,
  (select count(*) from spl_sets s where s.drug_id = d.id and s.role = 'generic'
     and not s.is_repackager) as generics,
  (select count(distinct j.generic_set_id) from v_current_judgement j
     join safety_events e on e.id = j.event_id
     where e.drug_id = d.id and j.status = 'not_propagated'
       and e.event_date < current_date - cast(:stale_days as integer)) as stale_generics,
  l.median_lag_days, l.p90_lag_days,
  (select max(event_date) from safety_events e where e.drug_id = d.id) as last_event_date
from drugs d
left join mv_drug_lag l on l.drug_id = d.id
where (cast(:q as text) is null or d.ingredient_norm ilike '%' || cast(:q as text) || '%')
  and (cast(:drug_id as uuid) is null or d.id = cast(:drug_id as uuid))
order by d.ingredient
limit :limit offset :offset
"""

_EVENTS = """
select e.id, e.drug_id, e.event_date, e.section_key, e.change_type, e.severity, e.claim_text,
  count(*) filter (where j.status = 'propagated') as propagated,
  count(*) filter (where j.status = 'partial') as partial,
  count(*) filter (where j.status = 'not_propagated') as not_propagated,
  count(*) filter (where j.status = 'insufficient_evidence') as insufficient_evidence
from safety_events e
left join v_current_judgement j on j.event_id = e.id
where (cast(:drug_id as uuid) is null or e.drug_id = cast(:drug_id as uuid))
  and (cast(:event_id as uuid) is null or e.id = cast(:event_id as uuid))
  and (cast(:severity as text) is null or e.severity = cast(:severity as text))
  and (cast(:section_key as text) is null or e.section_key = cast(:section_key as text))
group by e.id
order by e.event_date desc, e.section_key
limit :limit offset :offset
"""

_JUDGEMENTS = """
select j.id, j.event_id, j.status, j.lag_days, j.confidence, j.method, j.non_monotonic,
  j.evidence, j.model, j.first_version_date, fv.version as first_version_number,
  s.setid, s.title, s.labeler, s.is_repackager, s.latest_published,
  e.event_date, e.claim_text, e.drug_id, e.section_key
from v_current_judgement j
join spl_sets s on s.id = j.generic_set_id
join safety_events e on e.id = j.event_id
left join spl_versions fv on fv.id = j.first_version_id
where (cast(:event_id as uuid) is null or j.event_id = cast(:event_id as uuid))
  and (cast(:drug_id as uuid) is null or e.drug_id = cast(:drug_id as uuid))
  and (cast(:judgement_id as uuid) is null or j.id = cast(:judgement_id as uuid))
  and (cast(:status as text) is null or j.status = cast(:status as text))
  and (not :stale_only or (j.status = 'not_propagated'
       and e.event_date < current_date - cast(:stale_days as integer)))
order by e.event_date desc, s.title
limit :limit offset :offset
"""


class CatalogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _all(self, sql: str, params: dict[str, Any]) -> list[RowMapping]:
        result = await self._session.execute(text(sql), params)
        return list(result.mappings().all())

    async def drugs(
        self,
        *,
        stale_days: int,
        q: str | None = None,
        drug_id: uuid.UUID | None = None,
        limit: int = 25,
        offset: int = 0,
    ) -> list[RowMapping]:
        return await self._all(
            _DRUGS,
            {
                "q": q,
                "drug_id": drug_id,
                "stale_days": stale_days,
                "limit": limit,
                "offset": offset,
            },
        )

    async def events(
        self,
        *,
        drug_id: uuid.UUID | None = None,
        event_id: uuid.UUID | None = None,
        severity: str | None = None,
        section_key: str | None = None,
        limit: int = 25,
        offset: int = 0,
    ) -> list[RowMapping]:
        return await self._all(
            _EVENTS,
            {
                "drug_id": drug_id,
                "event_id": event_id,
                "severity": severity,
                "section_key": section_key,
                "limit": limit,
                "offset": offset,
            },
        )

    async def judgements(
        self,
        *,
        stale_days: int,
        event_id: uuid.UUID | None = None,
        drug_id: uuid.UUID | None = None,
        judgement_id: uuid.UUID | None = None,
        status: str | None = None,
        stale_only: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[RowMapping]:
        return await self._all(
            _JUDGEMENTS,
            {
                "event_id": event_id,
                "drug_id": drug_id,
                "judgement_id": judgement_id,
                "status": status,
                "stale_only": stale_only,
                "stale_days": stale_days,
                "limit": limit,
                "offset": offset,
            },
        )

    async def event_detail(self, event_id: uuid.UUID) -> RowMapping | None:
        rows = await self._all(
            """
            select e.id, e.drug_id, d.ingredient, e.event_date, e.section_key, e.change_type,
              e.severity, e.claim_text, e.brand_unit, s.setid as brand_setid,
              s.title as brand_title, v.version as brand_version
            from safety_events e
            join drugs d on d.id = e.drug_id
            join spl_sets s on s.id = e.brand_set_id
            join spl_versions v on v.id = e.to_version_id
            where e.id = :event_id
            """,
            {"event_id": event_id},
        )
        return rows[0] if rows else None

    async def section_text(self, setid: uuid.UUID, version: int, section_key: str) -> str | None:
        body = await self._session.scalar(
            text(
                """
                select t.body from spl_sets s
                join spl_versions v on v.spl_set_id = s.id
                join version_sections vs on vs.version_id = v.id
                join section_texts t on t.hash = vs.text_hash
                where s.setid = :setid and v.version = :version and vs.section_key = :key
                """
            ),
            {"setid": setid, "version": version, "key": section_key},
        )
        return str(body) if body is not None else None

    async def overview(self, stale_days: int) -> RowMapping:
        result = await self._session.execute(
            text(
                """
                select
                  (select count(*) from drugs) as drugs,
                  (select count(*) from safety_events) as events,
                  (select count(*) from v_current_judgement) as judgements,
                  (select percentile_cont(0.5) within group (order by lag_days)
                     from v_current_judgement where status = 'propagated') as median_lag_days,
                  (select count(*) from v_current_judgement j join safety_events e
                     on e.id = j.event_id where j.status = 'not_propagated'
                     and e.event_date < current_date - cast(:stale_days as integer)) as stale,
                  (select max(finished_at) from ingestion_runs
                     where kind = 'ingest_drug' and status in ('done', 'partial'))
                     as last_ingestion_at
                """
            ),
            {"stale_days": stale_days},
        )
        return result.mappings().one()
