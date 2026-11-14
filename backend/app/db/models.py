"""ORM mappings for supabase/migrations. The SQL files are the source of truth for the schema."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

SECTION_KEYS = (
    "boxed_warning",
    "warnings_precautions",
    "warnings",
    "precautions",
    "adverse_reactions",
    "contraindications",
    "drug_interactions",
    "specific_populations",
    "pregnancy",
)
APPL_TYPES = ("NDA", "ANDA", "BLA")
SET_ROLES = ("brand", "generic", "authorized_generic", "other")
CHANGE_TYPES = ("added", "strengthened", "modified")
SEVERITIES = ("boxed", "major", "moderate", "minor")
STATUSES = ("propagated", "partial", "not_propagated", "insufficient_evidence")
JUDGE_METHODS = (
    "baseline_exact",
    "baseline_unchanged",
    "baseline_lexical",
    "llm",
    "jev",
    "cascade",
    "human",
)
JOB_KINDS = ("fetch_set", "parse_version", "detect_events", "judge_pair", "refresh_views")
JOB_STATUSES = ("queued", "running", "done", "failed", "deferred")


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Base(DeclarativeBase):
    pass


class Drug(Base):
    __tablename__ = "drugs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    ingredient: Mapped[str] = mapped_column(Text, nullable=False)
    ingredient_norm: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    rxcui: Mapped[str | None] = mapped_column(Text)
    drug_class: Mapped[str | None] = mapped_column(Text)
    is_seed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created_at()


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("appl_type", "appl_no"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    drug_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("drugs.id", ondelete="CASCADE"), nullable=False
    )
    appl_type: Mapped[str] = mapped_column(Text, nullable=False)
    appl_no: Mapped[str] = mapped_column(Text, nullable=False)
    applicant: Mapped[str | None] = mapped_column(Text)
    trade_name: Mapped[str | None] = mapped_column(Text)
    is_rld: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    products: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'")
    )
    reference_application_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("applications.id")
    )
    link_method: Mapped[str | None] = mapped_column(Text)
    link_confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))


class SplSet(Base):
    __tablename__ = "spl_sets"

    id: Mapped[uuid.UUID] = _uuid_pk()
    setid: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, unique=True)
    drug_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("drugs.id", ondelete="CASCADE"), nullable=False
    )
    application_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("applications.id"))
    title: Mapped[str] = mapped_column(Text, nullable=False)
    labeler: Mapped[str | None] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    is_repackager: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    latest_version: Mapped[int | None] = mapped_column(Integer)
    latest_published: Mapped[date | None] = mapped_column(Date)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SplVersion(Base):
    __tablename__ = "spl_versions"
    __table_args__ = (UniqueConstraint("spl_set_id", "version"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    spl_set_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("spl_sets.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    published_date: Mapped[date] = mapped_column(Date, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    raw_sha256: Mapped[str | None] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SectionText(Base):
    __tablename__ = "section_texts"

    hash: Mapped[str] = mapped_column(Text, primary_key=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    char_len: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = _created_at()


class VersionSection(Base):
    __tablename__ = "version_sections"

    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("spl_versions.id", ondelete="CASCADE"), primary_key=True
    )
    section_key: Mapped[str] = mapped_column(Text, primary_key=True)
    loinc: Mapped[str | None] = mapped_column(Text)
    text_hash: Mapped[str] = mapped_column(ForeignKey("section_texts.hash"), nullable=False)


class SafetyEvent(Base):
    __tablename__ = "safety_events"
    __table_args__ = (UniqueConstraint("brand_set_id", "claim_hash"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    drug_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("drugs.id", ondelete="CASCADE"), nullable=False
    )
    brand_set_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("spl_sets.id", ondelete="CASCADE"), nullable=False
    )
    from_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("spl_versions.id"))
    to_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("spl_versions.id"), nullable=False)
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    section_key: Mapped[str] = mapped_column(Text, nullable=False)
    change_type: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    claim_hash: Mapped[str] = mapped_column(Text, nullable=False)
    brand_unit: Mapped[str] = mapped_column(Text, nullable=False)
    classifier: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    srlc_ref: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()


class PropagationJudgement(Base):
    __tablename__ = "propagation_judgements"
    __table_args__ = (UniqueConstraint("event_id", "generic_set_id", "method", "cache_key"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("safety_events.id", ondelete="CASCADE"), nullable=False
    )
    generic_set_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("spl_sets.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    first_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("spl_versions.id"))
    first_version_date: Mapped[date | None] = mapped_column(Date)
    lag_days: Mapped[int | None] = mapped_column(Integer)
    non_monotonic: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    evidence: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'")
    )
    method: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    cache_key: Mapped[str] = mapped_column(Text, nullable=False)
    trace_id: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'queued'"))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    run_after: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class GoldLabel(Base):
    __tablename__ = "gold_labels"
    __table_args__ = (UniqueConstraint("event_id", "generic_set_id", "annotator"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("safety_events.id", ondelete="CASCADE"), nullable=False
    )
    generic_set_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("spl_sets.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    first_version_number: Mapped[int | None] = mapped_column(Integer)
    split: Mapped[str] = mapped_column(Text, nullable=False)
    annotator: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()


class EvalRun(Base):
    __tablename__ = "eval_runs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    method: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(Text)
    split: Mapped[str] = mapped_column(Text, nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    langsmith_experiment: Mapped[str | None] = mapped_column(Text)
    git_sha: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()


class EvalItem(Base):
    __tablename__ = "eval_items"

    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("eval_runs.id", ondelete="CASCADE"), primary_key=True
    )
    gold_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("gold_labels.id", ondelete="CASCADE"), primary_key=True
    )
    predicted_status: Mapped[str] = mapped_column(Text, nullable=False)
    correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer)


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    params: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    stats: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LlmBudget(Base):
    __tablename__ = "llm_budget"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    provider: Mapped[str] = mapped_column(Text, primary_key=True)
    model: Mapped[str] = mapped_column(Text, primary_key=True)
    calls: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    tokens_in: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    tokens_out: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))


class TraceBudget(Base):
    __tablename__ = "trace_budget"

    month: Mapped[date] = mapped_column(Date, primary_key=True)
    traces: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))


class LlmCache(Base):
    __tablename__ = "llm_cache"

    cache_key: Mapped[str] = mapped_column(Text, primary_key=True)
    task: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    output: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = _created_at()


class LeafletCheck(Base):
    __tablename__ = "leaflet_checks"

    id: Mapped[uuid.UUID] = _uuid_pk()
    drug_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("drugs.id", ondelete="CASCADE"), nullable=False
    )
    country: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'BD'"))
    brand_name: Mapped[str] = mapped_column(Text, nullable=False)
    manufacturer: Mapped[str | None] = mapped_column(Text)
    registration_no: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    file_sha256: Mapped[str | None] = mapped_column(Text)
    leaflet_text: Mapped[str] = mapped_column(Text, nullable=False)
    results: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    counts: Mapped[dict[str, int]] = mapped_column(JSONB, nullable=False)
    consistency: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()


class Subscriber(Base):
    __tablename__ = "subscribers"

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(Text, nullable=False)
    email_norm: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    locale: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'en'"))
    frequency: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'weekly'"))
    min_severity: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'major'"))
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'pending'"))
    consent_version: Mapped[str] = mapped_column(Text, nullable=False)
    consented_at: Mapped[datetime] = _created_at()
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    unsubscribed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_digest_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created_at()


class Watchlist(Base):
    __tablename__ = "watchlists"

    subscriber_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("subscribers.id", ondelete="CASCADE"), primary_key=True
    )
    drug_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("drugs.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = _created_at()


class NotificationEvent(Base):
    __tablename__ = "notification_events"

    id: Mapped[uuid.UUID] = _uuid_pk()
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    drug_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("drugs.id", ondelete="CASCADE"), nullable=False
    )
    event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("safety_events.id", ondelete="CASCADE")
    )
    generic_set_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("spl_sets.id", ondelete="CASCADE")
    )
    dedupe_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'")
    )
    created_at: Mapped[datetime] = _created_at()


class EmailOutbox(Base):
    __tablename__ = "email_outbox"

    id: Mapped[uuid.UUID] = _uuid_pk()
    subscriber_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("subscribers.id", ondelete="CASCADE"), nullable=False
    )
    template: Mapped[str] = mapped_column(Text, nullable=False)
    locale: Mapped[str] = mapped_column(Text, nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    dedupe_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    context: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'")
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'queued'"))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    last_error: Mapped[str | None] = mapped_column(Text)
    provider_message_id: Mapped[str | None] = mapped_column(Text)
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created_at()


class IngredientSynonym(Base):
    __tablename__ = "ingredient_synonyms"

    alias_norm: Mapped[str] = mapped_column(Text, primary_key=True)
    ingredient_norm: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str | None] = mapped_column(Text)


class BdBrand(Base):
    __tablename__ = "bd_brands"
    __table_args__ = (UniqueConstraint("brand_norm", "strength", "dosage_form", "manufacturer"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    brand_name: Mapped[str] = mapped_column(Text, nullable=False)
    brand_norm: Mapped[str] = mapped_column(Text, nullable=False)
    generic_name: Mapped[str] = mapped_column(Text, nullable=False)
    generic_norm: Mapped[str] = mapped_column(Text, nullable=False)
    drug_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("drugs.id", ondelete="SET NULL"))
    strength: Mapped[str | None] = mapped_column(Text)
    dosage_form: Mapped[str | None] = mapped_column(Text)
    manufacturer: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    source_license: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()


class RagDoc(Base):
    __tablename__ = "rag_docs"
    __table_args__ = (UniqueConstraint("kind", "ref_id", "lang"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    ref_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    lang: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'en'"))
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ChatFeedback(Base):
    __tablename__ = "chat_feedback"

    id: Mapped[uuid.UUID] = _uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    message_id: Mapped[str] = mapped_column(Text, nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()


class EvalItemExtra(Base):
    __tablename__ = "eval_items_extra"

    id: Mapped[uuid.UUID] = _uuid_pk()
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    lang: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'en'"))
    question: Mapped[str] = mapped_column(Text, nullable=False)
    expected: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    split: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'test'"))
    created_at: Mapped[datetime] = _created_at()


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    actor: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    entity: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _created_at()
