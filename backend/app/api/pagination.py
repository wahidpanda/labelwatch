"""Opaque offset cursors: limit defaults to 25, max 100 (SPEC section 10)."""

import base64
import binascii
from typing import Annotated

from fastapi import Query

from app.errors import AppError

Limit = Annotated[int, Query(ge=1, le=100)]
Cursor = Annotated[str | None, Query(max_length=64)]


def decode_cursor(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        value = int(base64.urlsafe_b64decode(cursor.encode()).decode())
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise AppError(400, "The cursor is not valid.", title="Bad Request") from exc
    if value < 0:
        raise AppError(400, "The cursor is not valid.", title="Bad Request")
    return value


def encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(str(offset).encode()).decode()


def next_cursor(offset: int, limit: int, returned: int) -> str | None:
    return encode_cursor(offset + limit) if returned == limit else None
