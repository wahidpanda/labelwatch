import pytest
from httpx import AsyncClient

from tests.conftest import FakeHealthStore


@pytest.mark.parametrize("path", ["/healthz", "/api/v1/healthz"])
async def test_healthz_is_ok(client: AsyncClient, path: str) -> None:
    response = await client.get(path)
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readyz_reports_schema_and_build(client: AsyncClient) -> None:
    response = await client.get("/api/v1/readyz")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "ok",
        "schema_version": "0001",
        "build_sha": "test-sha",
    }


async def test_readyz_returns_503_when_database_unreachable(
    client: AsyncClient, health_store: FakeHealthStore
) -> None:
    health_store.fail = True
    response = await client.get("/readyz")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["database"] == "unreachable"
    assert body["schema_version"] is None
