"""Propagation judging and lag (SPEC section 8, steps D to H)."""

import hashlib
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.budget import BudgetExceededError
from app.db.models import PropagationJudgement, SafetyEvent, SplSet, SplVersion
from app.db.repositories.drugs import DrugRepository
from app.db.repositories.ingestion_runs import IngestionRunRepository
from app.db.repositories.labels import LabelRepository
from app.db.repositories.llm_cache import LlmCacheRepository
from app.ingest.normalize import hash_form, normalize_ingredient, split_units
from app.judge.retrieval import (
    EXACT_THRESHOLD,
    LEXICAL_FLOOR,
    ScoredUnit,
    rank_units,
    verify_quotes,
)
from app.llm.factory import LlmSchemaError, LlmUnavailableError, StructuredLLM, cache_key
from app.llm.prompts import JUDGE_SYSTEM, PROMPT_VERSION, judge_user
from app.llm.schemas import JudgeOut
from app.logging import get_logger

log = get_logger(__name__)


class StopJudging(Exception):  # noqa: N818 - control flow
    pass


@dataclass(frozen=True)
class Verdict:
    status: str
    method: str
    confidence: float
    quotes: list[str]
    rationale: str
    candidates: list[ScoredUnit]
    model: str | None = None

    @property
    def propagated(self) -> bool:
        return self.status == "propagated"


@dataclass
class JudgeStats:
    pairs: int = 0
    skipped_current: int = 0
    versions_judged: int = 0
    baseline: int = 0
    cache_hits: int = 0
    llm_calls: int = 0
    rejected_quotes: int = 0
    judgements: int = 0
    deferred: bool = False
    errors: list[str] = field(default_factory=list)

    def as_json(self) -> dict[str, Any]:
        data = {k: v for k, v in self.__dict__.items() if k != "errors"}
        return {**data, "errors": self.errors[:50], "error_count": len(self.errors)}


def judgement_key(event_id: uuid.UUID, set_id: uuid.UUID, latest_version_id: uuid.UUID) -> str:
    raw = f"{event_id}|{set_id}|{latest_version_id}|{PROMPT_VERSION}"
    return hashlib.sha256(raw.encode()).hexdigest()


class Judge:
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

    async def judge_drug(self, ingredient: str) -> JudgeStats:
        norm = normalize_ingredient(ingredient)
        stats = JudgeStats()
        async with self._sessions() as session:
            run_id = await IngestionRunRepository(session).start(
                "judge_drug", {"ingredient": norm, "max_calls": self._max_calls}
            )
            await session.commit()
        status, error = "done", None
        try:
            await self._judge(norm, stats)
        except StopJudging:
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
                await session.execute(text("refresh materialized view mv_drug_lag"))
                await session.commit()
            log.info("judge_drug_done", ingredient=norm, status=status, **stats.as_json())
        return stats

    async def _judge(self, norm: str, stats: JudgeStats) -> None:
        async with self._sessions() as session:
            drug = await DrugRepository(session).get_by_norm(norm)
            if drug is None:
                raise LookupError(f"Drug {norm!r} has not been ingested")
            events = list(
                await session.scalars(
                    select(SafetyEvent)
                    .where(SafetyEvent.drug_id == drug.id)
                    .order_by(SafetyEvent.event_date)
                )
            )
            generic_sets = list(
                await session.scalars(
                    select(SplSet).where(
                        SplSet.drug_id == drug.id,
                        SplSet.role == "generic",
                        SplSet.is_repackager.is_(False),
                    )
                )
            )
            labels = LabelRepository(session)
            versions = {s.id: await labels.parsed_versions(s.id) for s in generic_sets}
            existing = set(
                await session.scalars(
                    select(PropagationJudgement.cache_key).where(
                        PropagationJudgement.event_id.in_([e.id for e in events])
                    )
                )
            )
        for event in events:
            for spl_set in generic_sets:
                history = versions[spl_set.id]
                if not history:
                    continue
                stats.pairs += 1
                key = judgement_key(event.id, spl_set.id, history[-1].id)
                if key in existing:
                    stats.skipped_current += 1
                    continue
                await self._judge_pair(event, spl_set, history, key, stats)

    async def _judge_pair(
        self,
        event: SafetyEvent,
        spl_set: SplSet,
        history: list[SplVersion],
        key: str,
        stats: JudgeStats,
    ) -> None:
        after = [v for v in history if v.published_date >= event.event_date]
        search = after or history[-1:]
        checked: dict[int, Verdict] = {}

        async def verdict(index: int) -> Verdict:
            if index not in checked:
                checked[index] = await self._judge_version(event, search[index], stats)
            return checked[index]

        latest = await verdict(len(search) - 1)
        first: SplVersion | None = None
        if latest.propagated:
            # Assume the change persists once present; find the earliest propagated version.
            lo, hi = 0, len(search) - 1
            while lo < hi:
                mid = (lo + hi) // 2
                if (await verdict(mid)).propagated:
                    hi = mid
                else:
                    lo = mid + 1
            first = search[lo]
            # The version just before is known absent; one more back catches a dropped claim.
            non_monotonic = lo >= 2 and (await verdict(lo - 2)).propagated
        else:
            non_monotonic = False
        lag = (first.published_date - event.event_date).days if first else None
        evidence = {
            "quotes": latest.quotes,
            "rationale": latest.rationale,
            "candidates": [{"text": c.text, "score": c.score} for c in latest.candidates],
            "checked": [
                {"version": search[i].version, "status": v.status, "method": v.method}
                for i, v in sorted(checked.items())
            ],
            "present_before_event": not after and latest.propagated,
        }
        async with self._sessions() as session:
            await session.execute(
                insert(PropagationJudgement)
                .values(
                    event_id=event.id,
                    generic_set_id=spl_set.id,
                    status=latest.status,
                    first_version_id=first.id if first else None,
                    first_version_date=first.published_date if first else None,
                    lag_days=max(lag, 0) if lag is not None else None,
                    non_monotonic=non_monotonic,
                    evidence=evidence,
                    method=latest.method,
                    model=latest.model,
                    prompt_version=PROMPT_VERSION,
                    confidence=round(latest.confidence, 2),
                    cache_key=key,
                )
                .on_conflict_do_nothing()
            )
            await session.commit()
        stats.judgements += 1

    async def _judge_version(
        self, event: SafetyEvent, version: SplVersion, stats: JudgeStats
    ) -> Verdict:
        stats.versions_judged += 1
        async with self._sessions() as session:
            sections = await LabelRepository(session).sections_for_version(version.id)
        units = [u for _digest, body in sections.values() for u in split_units(body)]
        ranked = rank_units(event.brand_unit, units)
        if ranked and ranked[0].exact >= EXACT_THRESHOLD:
            stats.baseline += 1
            return Verdict(
                "propagated", "baseline_exact", 0.99, [ranked[0].text], "Same text.", ranked
            )
        if not ranked or ranked[0].score < LEXICAL_FLOOR:
            stats.baseline += 1
            return Verdict(
                "not_propagated", "baseline_lexical", 0.6, [], "No similar text found.", ranked
            )
        return await self._llm_verdict(event, ranked, stats)

    async def _llm_verdict(
        self, event: SafetyEvent, ranked: list[ScoredUnit], stats: JudgeStats
    ) -> Verdict:
        units = [c.text for c in ranked]
        inputs = {
            "claim": hash_form(event.claim_text),
            "brand": hash_form(event.brand_unit),
            "units": [hash_form(u) for u in units],
        }
        key = cache_key("judge", self._llm.family, inputs)
        async with self._sessions() as session:
            cached = await LlmCacheRepository(session).get(key)
        if cached is not None:
            stats.cache_hits += 1
            out, model = JudgeOut.model_validate(cached["output"]), str(cached["model"])
        else:
            if self._max_calls is not None and stats.llm_calls >= self._max_calls:
                stats.deferred = True
                raise StopJudging
            stats.llm_calls += 1
            try:
                result = await self._llm.invoke(
                    JudgeOut,
                    JUDGE_SYSTEM,
                    judge_user(event.claim_text, event.brand_unit, units),
                    metadata={"event_id": str(event.id), "drug_id": str(event.drug_id)},
                )
            except BudgetExceededError as exc:
                stats.deferred = True
                stats.errors.append(str(exc))
                raise StopJudging from exc
            except LlmUnavailableError as exc:
                stats.errors.append(f"llm unavailable: {exc}")
                raise StopJudging from exc
            except LlmSchemaError as exc:
                stats.errors.append(str(exc))
                return Verdict("insufficient_evidence", "llm", 0.0, [], "Invalid output.", ranked)
            out, model = result.output, f"{result.provider}:{result.model}"
            async with self._sessions() as session:
                await LlmCacheRepository(session).put(
                    key,
                    task="judge",
                    prompt_version=PROMPT_VERSION,
                    provider=result.provider,
                    model=result.model,
                    output={"output": out.model_dump(), "model": model},
                )
                await session.commit()
        if out.status in ("propagated", "partial") and not verify_quotes(out.quotes, units):
            stats.rejected_quotes += 1
            return Verdict(
                "insufficient_evidence",
                "llm",
                0.0,
                [],
                "Quotes not found in the label.",
                ranked,
                model,
            )
        return Verdict(out.status, "llm", out.confidence, out.quotes, out.rationale, ranked, model)
