from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator
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

    langsmith_tracing: bool = False
    langsmith_project: str = "label-lag-radar-dev"
    trace_sample_rate: float = Field(default=0.2, ge=0.0, le=1.0)

    db_size_limit_mb: int = 400
    stale_days: int = 90

    @field_validator("admin_emails", "cors_origins", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
