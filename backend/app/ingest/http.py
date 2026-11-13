"""The only outbound HTTP client: host allow-list, rate limit, retries with backoff."""

import asyncio
import random
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import asynccontextmanager
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from app import __version__
from app.logging import get_logger

ALLOWED_HOSTS = frozenset(
    {
        "dailymed.nlm.nih.gov",
        "api.fda.gov",
        "www.fda.gov",
        "www.accessdata.fda.gov",
        "rxnav.nlm.nih.gov",
    }
)
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})

log = get_logger(__name__)


class DisallowedHostError(ValueError):
    pass


class UpstreamError(RuntimeError):
    def __init__(self, url: str, status: int | None, message: str) -> None:
        super().__init__(f"{message} ({status}) for {url}")
        self.url = url
        self.status = status


def check_url(url: httpx.URL) -> None:
    if url.scheme != "https" or url.host not in ALLOWED_HOSTS:
        raise DisallowedHostError(f"Outbound request to {url.scheme}://{url.host} is not allowed")


def retry_after_seconds(value: str | None, now: float | None = None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(value).timestamp()
    except (TypeError, ValueError):
        return None
    return max(0.0, when - (now if now is not None else time.time()))


class RateLimiter:
    """Spaces calls at least 1/rps seconds apart."""

    def __init__(
        self,
        rps: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._interval = 1.0 / rps
        self._clock = clock
        self._sleep = sleep
        self._lock = asyncio.Lock()
        self._next_at = 0.0

    async def wait(self) -> None:
        async with self._lock:
            now = self._clock()
            if now < self._next_at:
                await self._sleep(self._next_at - now)
                now = self._next_at
            self._next_at = now + self._interval


class PoliteHttpClient:
    def __init__(
        self,
        contact_email: str,
        *,
        rps: float = 2.0,
        max_retries: int = 4,
        timeout: float = 30.0,
        backoff_base: float = 1.0,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        rng: random.Random | None = None,
    ) -> None:
        contact = f"; {contact_email}" if contact_email else ""
        self._client = httpx.AsyncClient(
            headers={"User-Agent": f"label-lag-radar/{__version__} (research{contact})"},
            timeout=httpx.Timeout(timeout),
            follow_redirects=True,
            transport=transport,
            event_hooks={"request": [self._check_request]},
        )
        self._limiter = RateLimiter(rps, sleep=sleep)
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._sleep = sleep
        self._rng = rng or random.Random()  # noqa: S311 - jitter, not crypto

    @staticmethod
    async def _check_request(request: httpx.Request) -> None:
        check_url(request.url)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "PoliteHttpClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    def _delay(self, attempt: int, response: httpx.Response | None) -> float:
        if response is not None:
            hinted = retry_after_seconds(response.headers.get("Retry-After"))
            if hinted is not None:
                return min(hinted, 120.0)
        return float(self._backoff_base * 2**attempt + self._rng.uniform(0, self._backoff_base))

    @asynccontextmanager
    async def stream(
        self, url: str, params: Mapping[str, Any] | None = None
    ) -> AsyncIterator[httpx.Response]:
        """Yield a successful streamed response; retries happen before the body is read."""
        check_url(httpx.URL(url))
        attempt = 0
        while True:
            await self._limiter.wait()
            try:
                request = self._client.build_request("GET", url, params=params)
                response = await self._client.send(request, stream=True)
            except httpx.TransportError as exc:
                if attempt >= self._max_retries:
                    raise UpstreamError(url, None, f"Transport error: {exc!r}") from exc
                delay = self._delay(attempt, None)
                log.warning("http_retry", url=url, error=type(exc).__name__, delay=delay)
            else:
                if response.status_code < 400:
                    try:
                        yield response
                    finally:
                        await response.aclose()
                    return
                await response.aclose()
                if response.status_code not in RETRY_STATUSES or attempt >= self._max_retries:
                    raise UpstreamError(url, response.status_code, "Upstream request failed")
                delay = self._delay(attempt, response)
                log.warning("http_retry", url=url, status=response.status_code, delay=delay)
            attempt += 1
            await self._sleep(delay)

    async def get_json(self, url: str, params: Mapping[str, Any] | None = None) -> Any:
        async with self.stream(url, params) as response:
            await response.aread()
            return response.json()
