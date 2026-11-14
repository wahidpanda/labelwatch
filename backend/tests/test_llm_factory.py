from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import date
from typing import Any

import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import Runnable, RunnableLambda

from app.config import Settings
from app.core.budget import BudgetExceededError, BudgetStore
from app.llm.factory import (
    LlmSchemaError,
    LlmUnavailableError,
    ProviderConfig,
    StructuredLLM,
    StructuredModel,
    Task,
    build_chat_model,
    cache_key,
    provider_configs,
)
from app.llm.schemas import ClassifyOut

GOOD = ClassifyOut(
    is_substantive=True, change_type="added", severity="major", claim="New warning.", reason="New."
)


class MemoryBudget:
    def __init__(self, used: dict[str, int] | None = None) -> None:
        self.used = dict(used or {})
        self.tokens: list[tuple[str, int, int]] = []

    async def llm_calls(self, day: date, provider: str) -> int:
        return self.used.get(provider, 0)

    async def record_llm_call(
        self, day: date, provider: str, model: str, *, tokens_in: int, tokens_out: int
    ) -> None:
        self.used[provider] = self.used.get(provider, 0) + 1
        self.tokens.append((provider, tokens_in, tokens_out))

    async def traces(self, month: date) -> int:
        return 0

    async def increment_traces(self, month: date) -> int:
        return 1

    async def database_size_mb(self) -> float:
        return 1.0


def scope_of(store: MemoryBudget) -> Callable[[], AbstractAsyncContextManager[BudgetStore]]:
    @asynccontextmanager
    async def scope() -> AsyncIterator[BudgetStore]:
        yield store

    return scope


class FakeModel:
    def __init__(self, answers: list[Any]) -> None:
        self.answers = list(answers)
        self.calls = 0

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Runnable[Any, Any]:
        async def run(_messages: Any) -> dict[str, Any]:
            self.calls += 1
            answer = self.answers.pop(0)
            if isinstance(answer, Exception):
                raise answer
            raw = AIMessage(
                content="",
                usage_metadata={"input_tokens": 10, "output_tokens": 3, "total_tokens": 13},
            )
            return {"raw": raw, "parsed": answer, "parsing_error": None}

        return RunnableLambda(run)


def configs(*providers: str) -> list[ProviderConfig]:
    return [ProviderConfig(p, f"{p}-model", daily_cap=5, rps=10.0, api_key="k") for p in providers]


def llm_with(models: dict[str, FakeModel], store: MemoryBudget, *providers: str) -> StructuredLLM:
    def builder(config: ProviderConfig, task: Task) -> StructuredModel:
        return models[config.provider]

    return StructuredLLM(
        "classify",
        configs(*providers),
        scope_of(store),
        builder=builder,
        today=lambda: date(2026, 1, 1),
    )


async def test_first_provider_answers_and_usage_is_recorded() -> None:
    store = MemoryBudget()
    llm = llm_with({"groq": FakeModel([GOOD])}, store, "groq")
    result = await llm.invoke(ClassifyOut, "sys", "user")
    assert result.output == GOOD
    assert result.provider == "groq"
    assert store.tokens == [("groq", 10, 3)]


async def test_falls_back_on_error_and_on_budget() -> None:
    store = MemoryBudget({"google_genai": 5})
    models = {
        "google_genai": FakeModel([]),
        "groq": FakeModel([RuntimeError("503")]),
        "ollama": FakeModel([GOOD]),
    }
    result = await llm_with(models, store, "google_genai", "groq", "ollama").invoke(
        ClassifyOut, "s", "u"
    )
    assert result.provider == "ollama"
    assert models["google_genai"].calls == 0


async def test_all_budgets_exhausted_raises_budget_error() -> None:
    store = MemoryBudget({"groq": 5})
    with pytest.raises(BudgetExceededError):
        await llm_with({"groq": FakeModel([])}, store, "groq").invoke(ClassifyOut, "s", "u")


async def test_all_providers_failing_raises_unavailable() -> None:
    store = MemoryBudget()
    with pytest.raises(LlmUnavailableError):
        await llm_with({"groq": FakeModel([TimeoutError()])}, store, "groq").invoke(
            ClassifyOut, "s", "u"
        )


async def test_schema_mismatch_retries_once_then_raises() -> None:
    store = MemoryBudget()
    model = FakeModel([None, GOOD])
    assert (
        await llm_with({"groq": model}, store, "groq").invoke(ClassifyOut, "s", "u")
    ).output == GOOD
    with pytest.raises(LlmSchemaError):
        await llm_with({"groq": FakeModel([None, None])}, store, "groq").invoke(
            ClassifyOut, "s", "u"
        )


async def test_no_configs_raises() -> None:
    llm = StructuredLLM("judge", [], scope_of(MemoryBudget()))
    assert not llm.available
    assert llm.family == "none"
    with pytest.raises(LlmUnavailableError):
        await llm.invoke(ClassifyOut, "s", "u")


def test_provider_configs_skip_missing_model_or_key() -> None:
    settings = Settings(
        _env_file=None,
        llm_provider_order=["google_genai", "groq", "openrouter", "ollama", "bogus"],
        google_api_key="g",
        llm_model_classify_google_genai="gemini-x",
        llm_model_classify_groq="llama-x",  # no groq key
        openrouter_api_key="o",
        llm_model_classify_openrouter="free/x",
        llm_model_classify_ollama="qwen",
    )
    result = provider_configs(settings, "classify")
    assert [c.provider for c in result] == ["google_genai", "openrouter", "ollama"]
    assert result[0].api_key == "g"
    assert result[1].base_url == "https://openrouter.ai/api/v1"
    assert result[2].base_url == "http://localhost:11434"
    assert provider_configs(settings, "judge") == []


def test_provider_order_is_parsed_from_csv() -> None:
    settings = Settings(_env_file=None, llm_provider_order="groq, ollama")
    assert settings.llm_provider_order == ["groq", "ollama"]


def test_cache_key_is_stable_and_input_sensitive() -> None:
    a = cache_key("classify", "groq:x", {"unit": "A", "section": "warnings"})
    b = cache_key("classify", "groq:x", {"section": "warnings", "unit": "A"})
    assert a == b
    assert a != cache_key("classify", "groq:y", {"unit": "A", "section": "warnings"})
    assert a != cache_key("judge", "groq:x", {"unit": "A", "section": "warnings"})


@pytest.mark.parametrize("provider", ["google_genai", "groq", "openrouter", "ollama"])
def test_build_chat_model_for_each_provider(provider: str) -> None:
    config = ProviderConfig(
        provider,
        "some-model",
        daily_cap=1,
        rps=1.0,
        api_key="test-key",
        base_url="http://localhost:11434" if provider == "ollama" else None,
    )
    model = build_chat_model(config, "assistant")
    assert hasattr(model, "with_structured_output")
