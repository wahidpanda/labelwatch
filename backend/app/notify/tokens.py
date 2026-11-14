"""HMAC-signed email tokens (confirm, manage, unsubscribe)."""

import hashlib
import hmac
import json
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode
from typing import Literal
from uuid import UUID

from app.errors import AppError

Purpose = Literal["confirm", "manage", "unsub"]
TTL = {"confirm": 48 * 3600, "manage": 365 * 24 * 3600, "unsub": 365 * 24 * 3600}


def _sign(secret: str, payload: bytes) -> str:
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def mint(secret: str, purpose: Purpose, subscriber_id: UUID) -> str:
    body = {
        "p": purpose,
        "s": str(subscriber_id),
        "e": int(time.time()) + TTL[purpose],
    }
    raw = json.dumps(body, separators=(",", ":")).encode()
    return urlsafe_b64encode(raw + b"." + _sign(secret, raw).encode()).decode()


def verify(secret: str, token: str, purpose: Purpose) -> UUID:
    try:
        decoded = urlsafe_b64decode(token.encode())
        raw, sig = decoded.rsplit(b".", 1)
        if not hmac.compare_digest(sig.decode(), _sign(secret, raw)):
            raise AppError(400, "Invalid token.")
        data = json.loads(raw)
        if data.get("p") != purpose:
            raise AppError(400, "Invalid token purpose.")
        if int(data.get("e", 0)) < time.time():
            raise AppError(400, "Token expired.")
        return UUID(str(data["s"]))
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        raise AppError(400, "Invalid token.") from exc
