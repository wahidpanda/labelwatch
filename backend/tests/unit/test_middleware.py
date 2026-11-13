from httpx import AsyncClient


async def test_valid_request_id_is_echoed(client: AsyncClient) -> None:
    response = await client.get("/healthz", headers={"x-request-id": "abc-123"})
    assert response.headers["x-request-id"] == "abc-123"


async def test_invalid_request_id_is_replaced(client: AsyncClient) -> None:
    response = await client.get("/healthz", headers={"x-request-id": "bad id <script>"})
    request_id = response.headers["x-request-id"]
    assert request_id != "bad id <script>"
    assert len(request_id) == 32


async def test_cors_allows_configured_origin_only(client: AsyncClient) -> None:
    allowed = await client.get("/healthz", headers={"origin": "http://localhost:5173"})
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
    denied = await client.get("/healthz", headers={"origin": "https://evil.example"})
    assert "access-control-allow-origin" not in denied.headers
