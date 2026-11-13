import pytest

from app.config import Settings


def test_comma_lists_are_split(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://a.test, http://b.test,,")
    monkeypatch.setenv("ADMIN_EMAILS", "one@example.com")
    settings = Settings(_env_file=None)
    assert settings.cors_origins == ["http://a.test", "http://b.test"]
    assert settings.admin_emails == ["one@example.com"]


def test_defaults_without_env() -> None:
    settings = Settings(_env_file=None)
    assert settings.db_size_limit_mb == 400
    assert settings.stale_days == 90
    assert settings.trace_sample_rate == 0.2
