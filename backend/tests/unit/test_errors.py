from http import HTTPStatus

from fastapi import FastAPI
from httpx import AsyncClient

from app.errors import PROBLEM_JSON, AppError


def _add_test_routes(app: FastAPI) -> None:
    @app.get("/_test/boom")
    async def boom() -> None:
        raise RuntimeError("secret internals")

    @app.get("/_test/app-error")
    async def app_error() -> None:
        raise AppError(409, "Already exists.", type_="https://example.test/conflict")

    @app.get("/_test/items")
    async def items(limit: int) -> dict[str, int]:
        return {"limit": limit}


async def test_not_found_is_problem_json(client: AsyncClient) -> None:
    response = await client.get("/api/v1/nope")
    assert response.status_code == 404
    assert response.headers["content-type"] == PROBLEM_JSON
    body = response.json()
    assert body["status"] == 404
    assert body["title"] == "Not Found"
    assert body["type"] == "about:blank"
    assert body["request_id"] == response.headers["x-request-id"]


async def test_validation_error_is_problem_json(app: FastAPI, client: AsyncClient) -> None:
    _add_test_routes(app)
    response = await client.get("/_test/items", params={"limit": "abc"})
    assert response.status_code == 422
    assert response.headers["content-type"] == PROBLEM_JSON
    body = response.json()
    assert body["title"] == HTTPStatus(422).phrase
    assert body["errors"][0]["loc"] == ["query", "limit"]


async def test_app_error_maps_to_problem(app: FastAPI, client: AsyncClient) -> None:
    _add_test_routes(app)
    response = await client.get("/_test/app-error")
    assert response.status_code == 409
    body = response.json()
    assert body["type"] == "https://example.test/conflict"
    assert body["detail"] == "Already exists."


async def test_unhandled_error_hides_details(app: FastAPI, client: AsyncClient) -> None:
    _add_test_routes(app)
    response = await client.get("/_test/boom")
    assert response.status_code == 500
    assert response.headers["content-type"] == PROBLEM_JSON
    body = response.json()
    assert "secret" not in body["detail"]
    assert body["request_id"]
