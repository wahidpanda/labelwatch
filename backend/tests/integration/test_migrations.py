import shutil
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.migrate import DEFAULT_MIGRATIONS_DIR, MigrationError, apply_migrations
from app.db.repositories.health import HealthRepository
from tests.integration.conftest import TEST_DATABASE_URL


def test_second_run_applies_nothing(migrated_db: list[list[str]]) -> None:
    first, second = migrated_db
    assert first[:2] == ["0001", "0002"]
    assert second == []


async def test_edited_migration_is_refused(migrated_db: list[list[str]], tmp_path: Path) -> None:
    for path in DEFAULT_MIGRATIONS_DIR.glob("*.sql"):
        shutil.copy(path, tmp_path / path.name)
    init = tmp_path / "0001_init.sql"
    init.write_text(init.read_text(encoding="utf-8") + "\n-- edited\n", encoding="utf-8")
    with pytest.raises(MigrationError, match="changed after it was applied"):
        await apply_migrations(TEST_DATABASE_URL, tmp_path)


async def test_rls_enabled_on_every_table(session: AsyncSession) -> None:
    rows = (
        await session.execute(
            text(
                "select c.relname, c.relrowsecurity from pg_class c "
                "join pg_namespace n on n.oid = c.relnamespace "
                "where n.nspname = 'public' and c.relkind = 'r'"
            )
        )
    ).all()
    tables = {name: rls for name, rls in rows}
    assert {"drugs", "spl_sets", "propagation_judgements", "schema_migrations"} <= set(tables)
    assert [name for name, rls in tables.items() if not rls] == []


async def test_no_rls_policies_exist(session: AsyncSession) -> None:
    count = await session.scalar(text("select count(*) from pg_policies where schemaname='public'"))
    assert count == 0


async def test_views_are_hidden_from_api_roles(session: AsyncSession) -> None:
    for role in ("anon", "authenticated"):
        for view in ("v_current_judgement", "mv_drug_lag"):
            allowed = await session.scalar(
                text("select has_table_privilege(:role, :view, 'select')"),
                {"role": role, "view": view},
            )
            assert allowed is False, f"{role} can read {view}"
    options = await session.scalar(
        text("select reloptions from pg_class where relname = 'v_current_judgement'")
    )
    assert "security_invoker=true" in options


async def test_materialized_view_refreshes(session: AsyncSession) -> None:
    await session.execute(text("refresh materialized view concurrently mv_drug_lag"))


async def test_readiness_reports_latest_schema_version(session: AsyncSession) -> None:
    repo = HealthRepository(session)
    await repo.ping()
    assert await repo.schema_version() == "0002"
