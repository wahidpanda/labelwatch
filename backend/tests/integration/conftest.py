"""Integration tests run against a disposable Postgres given by TEST_DATABASE_URL."""

import os
from collections.abc import AsyncIterator

import asyncpg
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.db.migrate import apply_migrations, to_asyncpg_dsn

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")

# Mimic Supabase: API roles exist and receive default grants on new tables.
_SUPABASE_ROLES = """
do $$
declare r text;
begin
  foreach r in array array['anon', 'authenticated'] loop
    if not exists (select 1 from pg_roles where rolname = r) then
      execute format('create role %I nologin', r);
    end if;
  end loop;
end $$;
grant usage on schema public to anon, authenticated;
alter default privileges in schema public grant all on tables to anon, authenticated;
"""


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    skip = pytest.mark.skip(reason="TEST_DATABASE_URL is not set")
    for item in items:
        if "tests/integration/" in item.nodeid:
            item.add_marker(pytest.mark.integration)
            if not TEST_DATABASE_URL:
                item.add_marker(skip)


@pytest.fixture(scope="session")
async def migrated_db() -> AsyncIterator[list[list[str]]]:
    conn = await asyncpg.connect(to_asyncpg_dsn(TEST_DATABASE_URL))
    try:
        await conn.execute("drop schema if exists public cascade; create schema public;")
        await conn.execute(_SUPABASE_ROLES)
    finally:
        await conn.close()
    first = await apply_migrations(TEST_DATABASE_URL)
    second = await apply_migrations(TEST_DATABASE_URL)
    yield [first, second]


@pytest.fixture(scope="session")
async def engine(migrated_db: list[list[str]]) -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine(TEST_DATABASE_URL)
    yield eng
    await eng.dispose()


@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """A session whose work is rolled back after each test, even if the code commits."""
    async with engine.connect() as conn:
        trans = await conn.begin()
        sess = AsyncSession(bind=conn, join_transaction_mode="create_savepoint")
        try:
            yield sess
        finally:
            await sess.close()
            await trans.rollback()
