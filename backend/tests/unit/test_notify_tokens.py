from uuid import uuid4

from app.notify import tokens


def test_token_round_trip() -> None:
    signing_key = "unit-test-hmac-key-not-a-real-credential"
    sub_id = uuid4()
    raw = tokens.mint(signing_key, "confirm", sub_id)
    assert tokens.verify(signing_key, raw, "confirm") == sub_id
