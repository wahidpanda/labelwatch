"""Forward-only SQL migration runner. Usage: python -m app.db.migrate"""

import argparse
import asyncio
import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path

import asyncpg

from app.config import get_settings
from app.logging import configure_logging, get_logger

log = get_logger(__name__)

DEFAULT_MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "supabase" / "migrations"
_FILENAME = re.compile(r"^(?P<version>\d{4})_(?P<name>[a-z0-9_]+)\.sql$")
# Arbitrary constant so concurrent runners serialise on one advisory lock.
_LOCK_ID = 7_316_204_551

_BOOTSTRAP = """
create table if not exists schema_migrations (
  version text primary key,
  name text not null,
  checksum text not null,
  applied_at timestamptz not null default now()
);
alter table schema_migrations enable row level security;
"""


class MigrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Migration:
    version: str
    name: str
    sql: str

    @property
    def checksum(self) -> str:
        # Normalise line endings so Windows and Linux checkouts hash the same.
        return hashlib.sha256(self.sql.replace("\r\n", "\n").encode()).hexdigest()


def discover(directory: Path) -> list[Migration]:
    migrations: list[Migration] = []
    seen: set[str] = set()
    for path in sorted(directory.glob("*.sql")):
        match = _FILENAME.match(path.name)
        if match is None:
            raise MigrationError(f"Bad migration filename: {path.name}")
        version = match["version"]
        if version in seen:
            raise MigrationError(f"Duplicate migration version: {version}")
        seen.add(version)
        sql = path.read_text(encoding="utf-8")
        migrations.append(Migration(version=version, name=match["name"], sql=sql))
    return migrations


def to_asyncpg_dsn(url: str) -> str:
    return re.sub(r"^postgresql\+\w+://", "postgresql://", url)


async def apply_migrations(dsn: str, directory: Path = DEFAULT_MIGRATIONS_DIR) -> list[str]:
    """Apply pending migrations in order. Returns the versions applied by this call."""
    migrations = discover(directory)
    conn = await asyncpg.connect(to_asyncpg_dsn(dsn), statement_cache_size=0, timeout=30)
    try:
        await conn.execute("select pg_advisory_lock($1)", _LOCK_ID)
        try:
            await conn.execute(_BOOTSTRAP)
            rows = await conn.fetch("select version, checksum from schema_migrations")
            applied = {row["version"]: row["checksum"] for row in rows}
            newly_applied: list[str] = []
            for migration in migrations:
                recorded = applied.get(migration.version)
                if recorded is not None:
                    if recorded != migration.checksum:
                        raise MigrationError(
                            f"Migration {migration.version}_{migration.name} changed after it "
                            "was applied. Add a new migration instead of editing it."
                        )
                    continue
                async with conn.transaction():
                    await conn.execute(migration.sql)
                    await conn.execute(
                        "insert into schema_migrations (version, name, checksum) "
                        "values ($1, $2, $3)",
                        migration.version,
                        migration.name,
                        migration.checksum,
                    )
                log.info("migration_applied", version=migration.version, name=migration.name)
                newly_applied.append(migration.version)
            return newly_applied
        finally:
            await conn.execute("select pg_advisory_unlock($1)", _LOCK_ID)
    finally:
        await conn.close()


async def repair_drifted_checksums(
    dsn: str,
    directory: Path = DEFAULT_MIGRATIONS_DIR,
    *,
    versions: set[str] | None = None,
) -> list[str]:
    """Sync checksums when migration SQL on disk was normalized but already applied in the DB."""
    migrations = {m.version: m for m in discover(directory)}
    conn = await asyncpg.connect(to_asyncpg_dsn(dsn), statement_cache_size=0, timeout=30)
    repaired: list[str] = []
    try:
        await conn.execute(_BOOTSTRAP)
        rows = await conn.fetch("select version, checksum from schema_migrations")
        for row in rows:
            version = row["version"]
            if version not in migrations:
                continue
            if versions is not None and version not in versions:
                continue
            expected = migrations[version].checksum
            if row["checksum"] != expected:
                await conn.execute(
                    "update schema_migrations set checksum = $1 where version = $2",
                    expected,
                    version,
                )
                log.warning(
                    "migration_checksum_repaired",
                    version=version,
                    name=migrations[version].name,
                )
                repaired.append(version)
        return repaired
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply Supabase SQL migrations.")
    parser.add_argument(
        "--repair-checksums",
        action="store_true",
        help="Update checksums for already-applied migrations whose files changed cosmetically.",
    )
    parser.add_argument(
        "--versions",
        nargs="*",
        metavar="VERSION",
        help="Limit --repair-checksums to these migration versions (e.g. 0005).",
    )
    args = parser.parse_args()

    settings = get_settings()
    configure_logging(settings.log_level, json=settings.env != "dev")
    directory = Path(os.environ.get("MIGRATIONS_DIR", DEFAULT_MIGRATIONS_DIR))
    version_filter = set(args.versions) if args.versions else None

    if args.repair_checksums:
        repaired = asyncio.run(
            repair_drifted_checksums(
                settings.database_url_migrations, directory, versions=version_filter
            )
        )
        log.info("checksum_repair_done", repaired=repaired)

    applied = asyncio.run(apply_migrations(settings.database_url_migrations, directory))
    log.info("migrations_done", applied=applied, up_to_date=not applied)


if __name__ == "__main__":
    main()
