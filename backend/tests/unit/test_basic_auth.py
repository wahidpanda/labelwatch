import base64

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from app.config import Settings
from app.main import create_app
from app.middleware_basic_auth import BasicAuthMiddleware


@pytest.fixture
def auth_settings() -> Settings:
    return Settings(
        _env_file=None,
        env="test",
        site_auth_enabled=True,
        site_auth_username="wahid",
        site_auth_password=SecretStr("wahid"),
        rate_limit_per_minute=1000,
    )


@pytest.mark.asyncio
async def test_basic_auth_blocks_api(auth_settings: Settings) -> None:
    app = create_app(auth_settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        denied = await client.get("/api/v1/methodology")
        assert denied.status_code == 401
        preflight = await client.options(
            "/api/v1/methodology",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert preflight.status_code == 200
        assert (await client.get("/healthz")).status_code == 200


def test_basic_auth_header_parsing(auth_settings: Settings) -> None:
    middleware = BasicAuthMiddleware(None, auth_settings)  # type: ignore[arg-type]
    token = base64.b64encode(b"wahid:wahid").decode()
    assert middleware._authorized(f"Basic {token}")
    assert not middleware._authorized("Bearer x")
    assert not middleware._authorized(f"Basic {base64.b64encode(b'wrong:wrong').decode()}")
