"""Import Bangladesh brand rows from CSV. Requires data/bd/LICENSE_NOTE.md and medicines.csv or --fixture."""

from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import get_settings
from app.db.models import BdBrand, Drug, IngredientSynonym
from app.db.session import create_engine, create_session_factory
from app.ingest.normalize import normalize_ingredient

BD_DIR = ROOT / "data" / "bd"
LICENSE = BD_DIR / "LICENSE_NOTE.md"
DEFAULT_CSV = BD_DIR / "medicines.csv"
FIXTURE = BD_DIR / "fixture_medicines.csv"
SYNONYMS = ROOT / "config" / "ingredient_synonyms.yaml"


def brand_norm(name: str) -> str:
    return normalize_ingredient(name.replace("®", " ").strip())


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


async def main(csv_path: Path, *, use_fixture: bool) -> None:
    if not LICENSE.is_file():
        raise SystemExit(f"Missing {LICENSE}")
    path = FIXTURE if use_fixture else csv_path
    if not path.is_file():
        raise SystemExit(f"Missing {path}")
    settings = get_settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    rows = load_rows(path)
    license_note = LICENSE.read_text(encoding="utf-8")[:200]
    async with factory() as session:
        if SYNONYMS.is_file():
            for alias, target in (
                yaml.safe_load(SYNONYMS.read_text(encoding="utf-8")) or {}
            ).items():
                await session.execute(
                    insert(IngredientSynonym)
                    .values(alias_norm=alias, ingredient_norm=target, source="config")
                    .on_conflict_do_nothing()
                )
        for row in rows:
            generic = row.get("generic_name", "").strip()
            if not generic:
                continue
            gnorm = normalize_ingredient(generic)
            drug = await session.scalar(select(Drug).where(Drug.ingredient_norm == gnorm).limit(1))
            strength = (row.get("strength") or "").strip() or None
            dosage_form = (row.get("dosage_form") or "").strip() or None
            manufacturer = (row.get("manufacturer") or "").strip() or None
            await session.execute(
                insert(BdBrand)
                .values(
                    brand_name=row["brand_name"].strip(),
                    brand_norm=brand_norm(row["brand_name"]),
                    generic_name=generic,
                    generic_norm=gnorm,
                    drug_id=drug.id if drug else None,
                    strength=strength,
                    dosage_form=dosage_form,
                    manufacturer=manufacturer,
                    source="fixture" if use_fixture else "medicines.csv",
                    source_license=license_note,
                )
                .on_conflict_do_nothing(
                    index_elements=["brand_norm", "strength", "dosage_form", "manufacturer"]
                )
            )
        await session.commit()
    await engine.dispose()
    print(f"imported {len(rows)} rows from {path.name}")  # noqa: T201


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", action="store_true", help="Use data/bd/fixture_medicines.csv")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    args = parser.parse_args()
    asyncio.run(main(args.csv, use_fixture=args.fixture))
