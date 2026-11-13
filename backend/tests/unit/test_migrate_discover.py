from pathlib import Path

import pytest

from app.db.migrate import (
    DEFAULT_MIGRATIONS_DIR,
    Migration,
    MigrationError,
    discover,
    to_asyncpg_dsn,
)


def test_repo_migrations_are_discovered_in_order() -> None:
    versions = [m.version for m in discover(DEFAULT_MIGRATIONS_DIR)]
    assert versions[:2] == ["0001", "0002"]
    assert versions == sorted(versions)


def test_checksum_ignores_line_endings() -> None:
    lf = Migration("0001", "init", "select 1;\nselect 2;\n")
    crlf = Migration("0001", "init", "select 1;\r\nselect 2;\r\n")
    assert lf.checksum == crlf.checksum


@pytest.mark.parametrize("filename", ["1_init.sql", "0001-init.sql", "0001_Init.sql"])
def test_bad_filenames_are_rejected(tmp_path: Path, filename: str) -> None:
    (tmp_path / filename).write_text("select 1;")
    with pytest.raises(MigrationError, match="Bad migration filename"):
        discover(tmp_path)


def test_duplicate_versions_are_rejected(tmp_path: Path) -> None:
    (tmp_path / "0001_a.sql").write_text("select 1;")
    (tmp_path / "0001_b.sql").write_text("select 2;")
    with pytest.raises(MigrationError, match="Duplicate"):
        discover(tmp_path)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("postgresql+asyncpg://u:p@h:6543/db", "postgresql://u:p@h:6543/db"),
        ("postgresql://u:p@h:5432/db", "postgresql://u:p@h:5432/db"),
    ],
)
def test_dsn_driver_suffix_is_stripped(url: str, expected: str) -> None:
    assert to_asyncpg_dsn(url) == expected
