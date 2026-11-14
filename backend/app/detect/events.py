"""Brand safety event detection (SPEC section 8, steps A to C)."""

import hashlib
import itertools
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.budget import BudgetExceededError
from app.db.models import SplSet, SplVersion
from app.db.repositories.drugs import DrugRepository
from app.db.repositories.events import EventRepository
from app.db.repositories.ingestion_runs import IngestionRunRepository
from app.db.repositories.labels import LabelRepository
from app.db.repositories.llm_cache import LlmCacheRepository
from app.detect.differ import UnitChange, diff_units
from app.ingest.normalize import hash_form, normalize_ingredient, split_units
from app.llm.factory import LlmSchemaError, LlmUnavailableError, StructuredLLM, cache_key
from app.llm.prompts import CLASSIFY_SYSTEM, PROMPT_VERSION, classify_user
from app.llm.schemas import ClassifyOut
from app.logging import get_logger

log = get_logger(__name__)

# Units this short are headings or cross-references ("5.1 Bleeding Risk", "[see Warnings]").
MIN_UNIT_CHARS = 30
_LETTERS = re.compile(r"[^a-z]+")


def claim_hash(section_key: str, unit: str) -> str:
    return hashlib.sha256(f"{section_key}|{hash_form(unit)}".encode()).hexdigest()


def is_trivial(unit: str) -> bool:
    return len(_LETTERS.sub("", hash_form(unit))) < MIN_UNIT_CHARS


@dataclass
class DetectStats:
    brand_sets: int = 0
    pairs: int = 0
    sections_changed: int = 0
    candidates: int = 0
    trivial: int = 0
    known: int = 0
    cache_hits: int = 0
    llm_calls: int = 0
    editorial: int = 0
    events_created: int = 0
    deferred: bool = False
    errors: list[str] = field(default_factory=list)

    def as_json(self) -> dict[str, Any]:
        data = {k: v for k, v in self.__dict__.items() if k != "errors"}
        return {**data, "errors": self.errors[:50], "error_count": len(self.errors)}


@dataclass(frozen=True)
class _Pair:
    spl_set: SplSet
    old: SplVersion
    new: SplVersion


class StopDetection(Exception):  # noqa: N818 - control flow, not an error for callers
    pass


class EventDetector:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        llm: StructuredLLM,
        *,
        max_calls: int | None = None,
    ) -> None:
        self._sessions = session_factory
        self._llm = llm
        self._max_calls = max_calls

    async def detect_drug(self, ingredient: str) -> DetectStats:
        norm = normalize_ingredient(ingredient)
        stats = DetectStats()
        async with self._sessions() as session:
            run_id = await IngestionRunRepository(session).start(
                "detect_events", {"ingredient": norm, "max_calls": self._max_calls}
            )
            await session.commit()
        status, error = "done", None
        try:
            await self._detect(norm, stats)
        except StopDetection:
            status = "partial"
        except Exception as exc:
            status, error = "failed", f"{type(exc).__name__}: {exc}"
            raise
        finally:
            if status == "done" and (stats.errors or stats.deferred):
                status = "partial"
            async with self._sessions() as session:
                await IngestionRunRepository(session).finish(
                    run_id, status=status, stats=stats.as_json(), error=error
                )
                await session.commit()
            log.info("detect_events_done", ingredient=norm, status=status, **stats.as_json())
        return stats

    async def _brand_sets(self, session: AsyncSession, drug_id: uuid.UUID) -> list[SplSet]:
        sets = list(
            await session.scalars(
                select(SplSet).where(SplSet.drug_id == drug_id, SplSet.role == "brand")
            )
        )
        active = [s for s in sets if not s.is_repackager]
        return active or sets

    async def _detect(self, norm: str, stats: DetectStats) -> None:
        async with self._sessions() as session:
            drug = await DrugRepository(session).get_by_norm(norm)
            if drug is None:
                raise LookupError(f"Drug {norm!r} has not been ingested")
            drug_id = drug.id
            pairs: list[_Pair] = []
            for spl_set in await self._brand_sets(session, drug_id):
                versions = await LabelRepository(session).parsed_versions(spl_set.id)
                stats.brand_sets += 1
                pairs.extend(_Pair(spl_set, a, b) for a, b in itertools.pairwise(versions))
        for pair in pairs:
            stats.pairs += 1
            await self._detect_pair(drug_id, pair, stats)

    async def _detect_pair(self, drug_id: uuid.UUID, pair: _Pair, stats: DetectStats) -> None:
        async with self._sessions() as session:
            labels = LabelRepository(session)
            old = await labels.sections_for_version(pair.old.id)
            new = await labels.sections_for_version(pair.new.id)
            known = await EventRepository(session).claim_hashes(pair.spl_set.id)
        old_everywhere = {hash_form(u) for _h, body in old.values() for u in split_units(body)}
        for key, (digest, body) in sorted(new.items()):
            before = old.get(key)
            if before is not None and before[0] == digest:
                continue
            stats.sections_changed += 1
            old_units = split_units(before[1]) if before else []
            for change in diff_units(old_units, split_units(body)):
                if change.kind == "removed" or change.new is None:
                    continue
                if change.kind == "added" and hash_form(change.new) in old_everywhere:
                    continue  # moved from another section
                await self._candidate(drug_id, pair, key, change, known, stats)

    async def _candidate(
        self,
        drug_id: uuid.UUID,
        pair: _Pair,
        section_key: str,
        change: UnitChange,
        known: set[str],
        stats: DetectStats,
    ) -> None:
        assert change.new is not None  # noqa: S101 - filtered by the caller
        stats.candidates += 1
        if is_trivial(change.new):
            stats.trivial += 1
            return
        digest = claim_hash(section_key, change.new)
        if digest in known:
            stats.known += 1
            return
        result = await self._classify(section_key, change, stats)
        if result is None:
            return
        output, model = result
        if not output.is_substantive or output.change_type == "editorial":
            stats.editorial += 1
            return
        severity = "boxed" if section_key == "boxed_warning" else output.severity
        async with self._sessions() as session:
            created = await EventRepository(session).create(
                drug_id=drug_id,
                brand_set_id=pair.spl_set.id,
                from_version_id=pair.old.id,
                to_version_id=pair.new.id,
                event_date=pair.new.published_date,
                section_key=section_key,
                change_type=output.change_type,
                severity=severity,
                claim_text=output.claim,
                claim_hash=digest,
                brand_unit=change.new,
                classifier={
                    **output.model_dump(),
                    "model": model,
                    "prompt_version": PROMPT_VERSION,
                    "diff_kind": change.kind,
                    "similarity": round(change.similarity, 3),
                    "old_unit": change.old,
                },
            )
            await session.commit()
        known.add(digest)
        if created is not None:
            stats.events_created += 1

    async def _classify(
        self, section_key: str, change: UnitChange, stats: DetectStats
    ) -> tuple[ClassifyOut, str] | None:
        assert change.new is not None  # noqa: S101 - filtered by the caller
        inputs = {
            "section": section_key,
            "kind": change.kind,
            "new": hash_form(change.new),
            "old": hash_form(change.old) if change.old else None,
        }
        key = cache_key("classify", self._llm.family, inputs)
        async with self._sessions() as session:
            cached = await LlmCacheRepository(session).get(key)
        if cached is not None:
            stats.cache_hits += 1
            return ClassifyOut.model_validate(cached["output"]), str(cached["model"])
        if self._max_calls is not None and stats.llm_calls >= self._max_calls:
            stats.deferred = True
            raise StopDetection
        stats.llm_calls += 1
        try:
            result = await self._llm.invoke(
                ClassifyOut,
                CLASSIFY_SYSTEM,
                classify_user(section_key, change.kind, change.new, change.old),
                metadata={"section_key": section_key},
            )
        except BudgetExceededError as exc:
            stats.deferred = True
            stats.errors.append(str(exc))
            raise StopDetection from exc
        except LlmUnavailableError as exc:
            stats.errors.append(f"llm unavailable: {exc}")
            raise StopDetection from exc
        except LlmSchemaError as exc:
            stats.errors.append(str(exc))
            return None
        model = f"{result.provider}:{result.model}"
        async with self._sessions() as session:
            await LlmCacheRepository(session).put(
                key,
                task="classify",
                prompt_version=PROMPT_VERSION,
                provider=result.provider,
                model=result.model,
                output={"output": result.output.model_dump(), "model": model},
            )
            await session.commit()
        return result.output, model
