from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    env: Literal["dev", "test", "prod"] = "dev"
    build_sha: str = "unknown"
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/label_lag_radar"
    database_url_migrations: str = "postgresql://postgres:postgres@localhost:5432/label_lag_radar"

    supabase_url: str = ""
    supabase_jwks_url: str = ""
    admin_emails: Annotated[list[str], NoDecode] = Field(default_factory=list)
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173"]
    )
    contact_email: str = ""

    llm_provider_order: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["google_genai", "groq", "ollama"]
    )
    google_api_key: SecretStr | None = None
    groq_api_key: SecretStr | None = None
    openrouter_api_key: SecretStr | None = None
    ollama_api_key: SecretStr | None = None
    ollama_base_url: str = "http://localhost:11434"
    # Model names change often on free tiers, so none are hardcoded.
    llm_model_classify_google_genai: str = ""
    llm_model_judge_google_genai: str = ""
    llm_model_assistant_google_genai: str = ""
    llm_model_classify_groq: str = ""
    llm_model_judge_groq: str = ""
    llm_model_assistant_groq: str = ""
    llm_model_classify_openrouter: str = ""
    llm_model_judge_openrouter: str = ""
    llm_model_assistant_openrouter: str = ""
    llm_model_classify_ollama: str = ""
    llm_model_judge_ollama: str = ""
    llm_model_assistant_ollama: str = ""
    llm_daily_cap_google_genai: int = 200
    llm_daily_cap_groq: int = 500
    llm_daily_cap_openrouter: int = 50
    llm_daily_cap_ollama: int = 100_000
    llm_rps_google_genai: float = 0.1
    llm_rps_groq: float = 0.3
    llm_rps_openrouter: float = 0.1
    llm_rps_ollama: float = 5.0

    langsmith_tracing: bool = False
    langsmith_project: str = "label-lag-radar-dev"
    trace_sample_rate: float = Field(default=0.2, ge=0.0, le=1.0)

    rate_limit_per_minute: int = 60
    db_size_limit_mb: int = 400
    stale_days: int = 90

    frontend_base_url: str = "http://localhost:5173"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: SecretStr | None = None
    smtp_security: Literal["starttls", "ssl", "none"] = "starttls"
    email_from_name: str = "Label Lag Radar"
    email_from_address: str = ""
    email_reply_to: str = ""
    email_footer_address: str = ""
    email_dry_run: bool = True
    email_daily_cap: int = 150
    email_token_secret: SecretStr | None = None
    turnstile_secret: SecretStr | None = None
    consent_version: str = "2026-11-14"

    jev_enabled: bool = False
    typesafe_api_key: SecretStr | None = None
    typesafe_api_base: str = "https://api.typesafe.ai"
    jev_model: str = "jev-latest"
    jev_timeout_s: int = 15
    jev_daily_cap: int = 500
    jev_conf_accept: float = Field(default=0.85, ge=0.0, le=1.0)

    rag_use_vectors: bool = False
    chat_max_tool_calls: int = 6
    chat_timeout_s: int = 25
    chat_rate_limit_per_min: int = 10

    site_auth_enabled: bool = False
    site_auth_username: str = ""
    site_auth_password: SecretStr | None = None
    langsmith_endpoint: str = "https://api.smith.langchain.com"

    @field_validator("admin_emails", "cors_origins", "llm_provider_order", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
