"""openFDA drugsfda lookups used to check medicine names before they are added."""

import re
from dataclasses import dataclass
from typing import Any

import httpx

from app.ingest.normalize import normalize_ingredient

DRUGSFDA_URL = "https://api.fda.gov/drug/drugsfda.json"
_SAFE = re.compile(r"[^a-z0-9 \-]+")


@dataclass(frozen=True)
class FdaName:
    name: str
    applications: int


class OpenFdaError(RuntimeError):
    """openFDA did not answer."""


def clean_query(value: str) -> str:
    return " ".join(_SAFE.sub(" ", value.lower()).split())


class OpenFdaClient:
    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    async def _get(self, params: dict[str, Any]) -> dict[str, Any] | None:
        try:
            response = await self._http.get(DRUGSFDA_URL, params=params, timeout=15)
        except httpx.HTTPError as exc:
            raise OpenFdaError(type(exc).__name__) from exc
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            raise OpenFdaError(f"HTTP {response.status_code}")
        data: dict[str, Any] = response.json()
        return data

    async def search(self, query: str, limit: int = 10) -> list[FdaName]:
        """Generic names starting with the query, with their FDA application counts."""
        words = clean_query(query).split()
        if not words:
            return []
        terms = " AND ".join(f"openfda.generic_name:{w}*" for w in words)
        data = await self._get(
            {"search": terms, "count": "openfda.generic_name.exact", "limit": limit}
        )
        results = (data or {}).get("results") or []
        return [FdaName(str(r["term"]).lower(), int(r["count"])) for r in results]

    async def exists(self, name: str) -> bool:
        ingredient = normalize_ingredient(clean_query(name))
        if not ingredient:
            return False
        data = await self._get({"search": f'openfda.generic_name:"{ingredient}"', "limit": 1})
        total = ((data or {}).get("meta") or {}).get("results", {}).get("total", 0)
        return int(total) > 0
