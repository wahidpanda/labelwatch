import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.pagination import decode_cursor, encode_cursor, next_cursor
from app.errors import AppError, register_error_handlers
from app.middleware import RateLimitMiddleware, SecurityHeadersMiddleware


def test_cursor_round_trip_and_rejects_garbage() -> None:
    assert decode_cursor(None) == 0
    assert decode_cursor(encode_cursor(50)) == 50
    assert next_cursor(0, 25, 25) == encode_cursor(25)
    assert next_cursor(0, 25, 3) is None
    for bad in ("!!", encode_cursor(-1), "YWJj"):
        with pytest.raises(AppError):
            decode_cursor(bad)


def _app(clock: list[float]) -> FastAPI:
    app = FastAPI()

    @app.get("/api/v1/ping")
    async def ping() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/healthz")
    async def health() -> dict[str, bool]:
        return {"ok": True}

    register_error_handlers(app)
    app.add_middleware(RateLimitMiddleware, per_minute=2, clock=lambda: clock[0])
    app.add_middleware(SecurityHeadersMiddleware)
    return app


async def test_rate_limit_per_ip_and_window_reset() -> None:
    clock = [0.0]
    transport = ASGITransport(app=_app(clock))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/api/v1/ping")).status_code == 200
        assert (await client.get("/api/v1/ping")).status_code == 200
        limited = await client.get("/api/v1/ping")
        assert limited.status_code == 429
        assert limited.headers["content-type"] == "application/problem+json"
        assert "retry-after" in limited.headers
        other = await client.get("/api/v1/ping", headers={"x-forwarded-for": "10.0.0.9"})
        assert other.status_code == 200
        assert (await client.get("/healthz")).status_code == 200  # probes are never limited
        clock[0] = 61.0
        assert (await client.get("/api/v1/ping")).status_code == 200


async def test_security_headers_present() -> None:
    transport = ASGITransport(app=_app([0.0]))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/ping")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "default-src 'none'" in response.headers["content-security-policy"]
