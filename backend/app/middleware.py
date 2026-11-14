import re
import time
import uuid
from collections.abc import Callable

import structlog
from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.errors import problem_response
from app.logging import get_logger

REQUEST_ID_HEADER = "x-request-id"
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

log = get_logger("app.access")


class RequestContextMiddleware:
    """Assigns a request id, binds it to logs, and writes one access log line per request."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = next(
            (v.decode("latin-1") for k, v in scope["headers"] if k == REQUEST_ID_HEADER.encode()),
            "",
        )
        request_id = incoming if _VALID_REQUEST_ID.match(incoming) else uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id

        status_code = 500
        start = time.perf_counter()

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        structlog.contextvars.bind_contextvars(request_id=request_id)
        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            log.info(
                "request",
                method=scope["method"],
                route=scope["path"],
                status=status_code,
                latency_ms=round((time.perf_counter() - start) * 1000, 1),
            )
            structlog.contextvars.unbind_contextvars("request_id")


SECURITY_HEADERS = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "strict-origin-when-cross-origin",
    "permissions-policy": "camera=(), geolocation=(), microphone=(self)",
    "content-security-policy": "default-src 'none'; frame-ancestors 'none'",
    "strict-transport-security": "max-age=31536000; includeSubDomains",
}


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        docs = scope["path"].startswith("/api/docs")

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in SECURITY_HEADERS.items():
                    if docs and name == "content-security-policy":
                        continue  # Swagger UI loads its own scripts and styles.
                    headers.setdefault(name, value)
            await send(message)

        await self.app(scope, receive, send_wrapper)


class RateLimitMiddleware:
    """Fixed one-minute window per client IP for /api/v1. In memory, so per process."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        per_minute: int = 60,
        clock: Callable[[], float] = time.monotonic,
        max_clients: int = 10_000,
    ) -> None:
        self.app = app
        self.per_minute = per_minute
        self._clock = clock
        self._max_clients = max_clients
        self._windows: dict[str, tuple[int, int]] = {}

    def _client(self, scope: Scope) -> str:
        for key, value in scope["headers"]:
            if key == b"x-forwarded-for":
                return str(value.decode("latin-1")).split(",")[0].strip()
        client = scope.get("client")
        return str(client[0]) if client else "unknown"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith("/api/v1/"):
            await self.app(scope, receive, send)
            return
        window = int(self._clock() // 60)
        client = self._client(scope)
        start, count = self._windows.get(client, (window, 0))
        if start != window:
            start, count = window, 0
        count += 1
        if len(self._windows) >= self._max_clients and client not in self._windows:
            self._windows.clear()
        self._windows[client] = (start, count)
        if count > self.per_minute:
            retry = str(int(60 - self._clock() % 60) + 1)
            response = problem_response(
                Request(scope),
                429,
                "Too many requests. Please slow down.",
                headers={"retry-after": retry},
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
