"""Chat models per task from env config, with budget-aware provider fallback (SPEC 11.1).

Fallback is done here rather than with Runnable.with_fallbacks so that each provider's daily
cap is checked before its call and usage is recorded against the provider that answered.
"""

import hashlib
import json
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Literal, Protocol

from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.rate_limiters import InMemoryRateLimiter
from langchain_core.runnables import Runnable, RunnableConfig
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.core.budget import BudgetExceededError, BudgetStore, check_llm_budget, record_llm_usage
from app.db.repositories.budget import BudgetRepository
from app.llm.prompts import PROMPT_VERSION
from app.logging import get_logger

log = get_logger(__name__)

Task = Literal["classify", "judge", "assistant"]
PROVIDERS = ("google_genai", "groq", "openrouter", "ollama")
API_KEY_FIELDS = {
    "google_genai": "google_api_key",
    "groq": "groq_api_key",
    "openrouter": "openrouter_api_key",
    "ollama": "ollama_api_key",
}
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class LlmUnavailableError(RuntimeError):
    """No configured provider produced an answer."""


class LlmSchemaError(RuntimeError):
    """The model answered twice without matching the output schema."""


@dataclass(frozen=True)
class ProviderConfig:
    provider: str
    model: str
    daily_cap: int
    rps: float
    api_key: str | None = None
    base_url: str | None = None

    @property
    def family(self) -> str:
        return f"{self.provider}:{self.model}"


def provider_configs(settings: Settings, task: Task) -> list[ProviderConfig]:
    configs = []
    for provider in settings.llm_provider_order:
        if provider not in PROVIDERS:
            log.warning("unknown_llm_provider", provider=provider)
            continue
        model = getattr(settings, f"llm_model_{task}_{provider}", "")
        if not model:
            continue
        secret = getattr(settings, API_KEY_FIELDS[provider])
        api_key = secret.get_secret_value() if secret is not None else None
        if provider != "ollama" and not api_key:
            continue
        configs.append(
            ProviderConfig(
                provider=provider,
                model=model,
                daily_cap=getattr(settings, f"llm_daily_cap_{provider}"),
                rps=getattr(settings, f"llm_rps_{provider}"),
                api_key=api_key,
                base_url=(
                    OPENROUTER_BASE_URL
                    if provider == "openrouter"
                    else settings.ollama_base_url
                    if provider == "ollama"
                    else None
                ),
            )
        )
    return configs


class StructuredModel(Protocol):
    def with_structured_output(self, schema: Any, **kwargs: Any) -> Runnable[Any, Any]: ...


ModelBuilder = Callable[[ProviderConfig, Task], StructuredModel]


def build_chat_model(config: ProviderConfig, task: Task) -> StructuredModel:
    limiter = InMemoryRateLimiter(
        requests_per_second=config.rps, check_every_n_seconds=0.1, max_bucket_size=1
    )
    kwargs: dict[str, Any] = {
        "temperature": 0.2 if task == "assistant" else 0.0,
        "rate_limiter": limiter,
        "max_retries": 2,
    }
    if config.provider == "openrouter":
        return init_chat_model(  # type: ignore[no-any-return]
            config.model,
            model_provider="openai",
            base_url=config.base_url,
            api_key=config.api_key,
            **kwargs,
        )
    if config.provider == "ollama":
        kwargs.pop("max_retries")
        return init_chat_model(  # type: ignore[no-any-return]
            config.model, model_provider="ollama", base_url=config.base_url, **kwargs
        )
    return init_chat_model(  # type: ignore[no-any-return]
        config.model, model_provider=config.provider, api_key=config.api_key, **kwargs
    )


def cache_key(task: Task, family: str, inputs: dict[str, Any]) -> str:
    canonical = json.dumps(
        {"task": task, "prompt_version": PROMPT_VERSION, "family": family, "inputs": inputs},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class LlmResult[T: BaseModel]:
    output: T
    provider: str
    model: str


BudgetScope = Callable[[], AbstractAsyncContextManager[BudgetStore]]


class StructuredLLM:
    """Calls one task's providers in order until one returns a valid structured answer."""

    def __init__(
        self,
        task: Task,
        configs: list[ProviderConfig],
        budget: BudgetScope,
        *,
        builder: ModelBuilder = build_chat_model,
        today: Callable[[], date] = lambda: datetime.now(UTC).date(),
    ) -> None:
        self.task = task
        self._configs = configs
        self._budget = budget
        self._builder = builder
        self._today = today
        self._models: dict[str, StructuredModel] = {}

    @property
    def available(self) -> bool:
        return bool(self._configs)

    @property
    def family(self) -> str:
        return self._configs[0].family if self._configs else "none"

    def _model(self, config: ProviderConfig) -> StructuredModel:
        if config.family not in self._models:
            self._models[config.family] = self._builder(config, self.task)
        return self._models[config.family]

    async def invoke[T: BaseModel](
        self,
        schema: type[T],
        system: str,
        user: str | list[str | dict[str, Any]],
        *,
        metadata: dict[str, Any] | None = None,
    ) -> LlmResult[T]:
        """`user` is text, or LangChain content blocks when images are attached."""
        if not self._configs:
            raise LlmUnavailableError(f"No LLM provider is configured for {self.task}")
        budget_errors: list[BudgetExceededError] = []
        failures: list[str] = []
        for config in self._configs:
            today = self._today()
            async with self._budget() as store:
                try:
                    await check_llm_budget(store, config.provider, config.daily_cap, today)
                except BudgetExceededError as exc:
                    budget_errors.append(exc)
                    continue
            method = "json_schema" if config.provider == "google_genai" else "function_calling"
            runnable = self._model(config).with_structured_output(
                schema, method=method, include_raw=True
            )
            run_config: RunnableConfig = {
                "tags": [self.task],
                "metadata": {
                    **(metadata or {}),
                    "prompt_version": PROMPT_VERSION,
                    "provider": config.provider,
                    "model": config.model,
                },
            }
            messages = [SystemMessage(content=system), HumanMessage(content=user)]
            for _attempt in range(2):
                try:
                    result = await runnable.ainvoke(messages, config=run_config)
                except Exception as exc:
                    log.warning(
                        "llm_call_failed", provider=config.provider, error=type(exc).__name__
                    )
                    failures.append(f"{config.provider}: {type(exc).__name__}")
                    break
                await self._record(config, today, result.get("raw"))
                parsed = result.get("parsed")
                if isinstance(parsed, schema):
                    return LlmResult(parsed, config.provider, config.model)
                log.warning("llm_schema_mismatch", provider=config.provider, task=self.task)
            else:
                raise LlmSchemaError(f"{config.family} did not match {schema.__name__}")
        if budget_errors and not failures:
            raise budget_errors[-1]
        raise LlmUnavailableError("; ".join(failures) or "No provider answered")

    async def _record(self, config: ProviderConfig, today: date, raw: Any) -> None:
        usage = getattr(raw, "usage_metadata", None) or {}
        async with self._budget() as store:
            await record_llm_usage(
                store,
                config.provider,
                config.model,
                today,
                tokens_in=int(usage.get("input_tokens", 0)),
                tokens_out=int(usage.get("output_tokens", 0)),
            )


def budget_scope(session_factory: async_sessionmaker[AsyncSession]) -> BudgetScope:
    @asynccontextmanager
    async def scope() -> AsyncIterator[BudgetStore]:
        async with session_factory() as session:
            yield BudgetRepository(session)
            await session.commit()

    return scope


def structured_llm(
    settings: Settings, task: Task, session_factory: async_sessionmaker[AsyncSession]
) -> StructuredLLM:
    return StructuredLLM(task, provider_configs(settings, task), budget_scope(session_factory))
