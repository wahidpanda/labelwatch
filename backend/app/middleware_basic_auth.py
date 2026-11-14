"""Optional HTTP Basic auth for the public API."""

import base64
import hmac

from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import Settings


class BasicAuthMiddleware:
    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self._enabled = settings.site_auth_enabled
        self._user = settings.site_auth_username
        password = settings.site_auth_password
        self._password = password.get_secret_value() if password is not None else ""

    def _exempt(self, path: str) -> bool:
        return path in ("/healthz", "/readyz") or not path.startswith("/api/v1/")

    def _authorized(self, header: str) -> bool:
        if not header.lower().startswith("basic "):
            return False
        try:
            decoded = base64.b64decode(header.split(" ", 1)[1]).decode("utf-8")
            user, pw = decoded.split(":", 1)
        except (ValueError, UnicodeDecodeError):
            return False
        user_ok = hmac.compare_digest(user, self._user)
        pw_ok = hmac.compare_digest(pw, self._password)
        return user_ok and pw_ok and bool(self._user) and bool(self._password)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self._enabled or self._exempt(scope["path"]):
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        if self._authorized(request.headers.get("authorization", "")):
            await self.app(scope, receive, send)
            return
        response = Response(
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="Label Lag Radar"'},
            content="Authentication required.",
        )
        await response(scope, receive, send)
