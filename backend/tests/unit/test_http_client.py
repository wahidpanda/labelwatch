import random

import httpx
import pytest

from app.ingest.http import (
    DisallowedHostError,
    PoliteHttpClient,
    RateLimiter,
    UpstreamError,
    retry_after_seconds,
)

BASE = "https://dailymed.nlm.nih.gov/dailymed/services/v2"


class Sleeper:
    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


def make_client(handler: httpx.MockTransport, sleeper: Sleeper) -> PoliteHttpClient:
    return PoliteHttpClient(
        "me@example.com",
        rps=1000,
        transport=handler,
        sleep=sleeper,
        rng=random.Random(0),
        max_retries=2,
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.example/x",
        "http://dailymed.nlm.nih.gov/x",
        "https://dailymed.nlm.nih.gov.evil.example/x",
        "https://169.254.169.254/latest/meta-data",
    ],
)
async def test_disallowed_hosts_are_rejected(url: str) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200)

    async with make_client(httpx.MockTransport(handler), Sleeper()) as client:
        with pytest.raises(DisallowedHostError):
            await client.get_json(url)
    assert calls == []


async def test_redirect_to_disallowed_host_is_blocked() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "https://evil.example/steal"})

    async with make_client(httpx.MockTransport(handler), Sleeper()) as client:
        with pytest.raises(DisallowedHostError):
            await client.get_json(f"{BASE}/spls.json")


async def test_user_agent_includes_contact_email() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["User-Agent"])
        return httpx.Response(200, json={"ok": True})

    async with make_client(httpx.MockTransport(handler), Sleeper()) as client:
        assert await client.get_json(f"{BASE}/spls.json") == {"ok": True}
    assert "me@example.com" in seen[0]


async def test_retries_429_honouring_retry_after_then_succeeds() -> None:
    responses = [
        httpx.Response(429, headers={"Retry-After": "7"}),
        httpx.Response(503),
        httpx.Response(200, json={"n": 1}),
    ]
    sleeper = Sleeper()
    async with make_client(httpx.MockTransport(lambda r: responses.pop(0)), sleeper) as client:
        assert await client.get_json(f"{BASE}/spls.json") == {"n": 1}
    retry_sleeps = [s for s in sleeper.calls if s >= 0.5]
    assert retry_sleeps[0] == 7.0
    assert 2.0 <= retry_sleeps[1] <= 3.0


async def test_gives_up_after_max_retries() -> None:
    async with make_client(httpx.MockTransport(lambda r: httpx.Response(500)), Sleeper()) as c:
        with pytest.raises(UpstreamError) as excinfo:
            await c.get_json(f"{BASE}/spls.json")
    assert excinfo.value.status == 500


async def test_client_errors_are_not_retried() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(404)

    async with make_client(httpx.MockTransport(handler), Sleeper()) as client:
        with pytest.raises(UpstreamError):
            await client.get_json(f"{BASE}/spls/x.json")
    assert len(calls) == 1


async def test_transport_errors_are_retried() -> None:
    attempts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        if len(attempts) < 3:
            raise httpx.ConnectError("boom", request=request)
        return httpx.Response(200, json=[])

    async with make_client(httpx.MockTransport(handler), Sleeper()) as client:
        assert await client.get_json(f"{BASE}/spls.json") == []
    assert len(attempts) == 3


async def test_transport_errors_eventually_raise() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    async with make_client(httpx.MockTransport(handler), Sleeper()) as client:
        with pytest.raises(UpstreamError, match="Transport error"):
            await client.get_json(f"{BASE}/spls.json")


async def test_rate_limiter_spaces_calls() -> None:
    now = [100.0]
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    limiter = RateLimiter(2.0, clock=lambda: now[0], sleep=fake_sleep)
    for _ in range(3):
        await limiter.wait()
    assert sleeps == [0.5, 0.5]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("", None),
        ("12", 12.0),
        ("-3", 0.0),
        ("not a date", None),
        ("Wed, 21 Oct 2015 07:28:10 GMT", 10.0),
    ],
)
def test_retry_after_parsing(value: str | None, expected: float | None) -> None:
    now = 1445412480.0  # 2015-10-21 07:28:00 GMT
    assert retry_after_seconds(value, now=now) == expected
