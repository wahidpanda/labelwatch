from typing import Protocol

from pydantic import BaseModel

from app.logging import get_logger

log = get_logger(__name__)


class HealthOut(BaseModel):
    status: str


class ReadinessOut(BaseModel):
    status: str
    database: str
    schema_version: str | None
    build_sha: str


class HealthStore(Protocol):
    async def ping(self) -> None: ...

    async def schema_version(self) -> str | None: ...


class HealthService:
    def __init__(self, store: HealthStore, build_sha: str) -> None:
        self._store = store
        self._build_sha = build_sha

    async def readiness(self) -> ReadinessOut:
        try:
            await self._store.ping()
            schema_version = await self._store.schema_version()
        except Exception as exc:  # any driver or network failure means not ready
            log.warning("readiness_db_unreachable", error=type(exc).__name__)
            return ReadinessOut(
                status="unavailable",
                database="unreachable",
                schema_version=None,
                build_sha=self._build_sha,
            )
        return ReadinessOut(
            status="ok", database="ok", schema_version=schema_version, build_sha=self._build_sha
        )
