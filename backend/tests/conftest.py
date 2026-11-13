from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.deps import get_health_service
from app.main import create_app
from app.services.health import HealthService


class FakeHealthStore:
    def __init__(self, *, fail: bool = False, version: str | None = "0001") -> None:
        self.fail = fail
        self.version = version

    async def ping(self) -> None:
        if self.fail:
            raise ConnectionError("database down")

    async def schema_version(self) -> str | None:
        return self.version


@pytest.fixture
def settings() -> Settings:
    return Settings(env="test", build_sha="test-sha", cors_origins=["http://localhost:5173"])


@pytest.fixture
def health_store() -> FakeHealthStore:
    return FakeHealthStore()


@pytest.fixture
def app(settings: Settings, health_store: FakeHealthStore) -> FastAPI:
    application = create_app(settings)
    application.dependency_overrides[get_health_service] = lambda: HealthService(
        health_store, build_sha=settings.build_sha
    )
    return application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
