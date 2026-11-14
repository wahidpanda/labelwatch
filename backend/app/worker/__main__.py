"""Worker CLI. Example: python -m app.worker ingest --drug warfarin --drug montelukast"""

import argparse
import asyncio
import sys
from collections.abc import Sequence

from app.config import Settings, get_settings
from app.db.session import create_engine, create_session_factory
from app.detect.events import EventDetector
from app.ingest.dailymed import DailyMedClient
from app.ingest.http import PoliteHttpClient
from app.ingest.normalize import normalize_ingredient
from app.ingest.orange_book import download_products
from app.ingest.pipeline import IngestMode, IngestPipeline
from app.ingest.seeds import load_seed_drugs
from app.llm.factory import structured_llm
from app.logging import configure_logging, get_logger

log = get_logger("app.worker")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.worker")
    commands = parser.add_subparsers(dest="command", required=True)
    ingest = commands.add_parser("ingest", help="Ingest DailyMed labels for seed drugs")
    source = ingest.add_mutually_exclusive_group(required=True)
    source.add_argument("--drug", action="append", help="Ingredient name; repeatable")
    source.add_argument("--seed", action="store_true", help="All drugs in config/seed_drugs.yaml")
    source.add_argument("--start-with", action="store_true", help="The start_with seed subset")
    ingest.add_argument(
        "--mode", choices=[m.value for m in IngestMode], default=IngestMode.VERSIONS.value
    )
    detect = commands.add_parser("detect", help="Detect brand safety events for ingested drugs")
    detect.add_argument("--drug", action="append", required=True, help="Ingredient; repeatable")
    detect.add_argument("--max-calls", type=int, default=None, help="Cap on LLM calls per drug")
    return parser


def resolve_drugs(args: argparse.Namespace) -> list[str]:
    names = list(args.drug or load_seed_drugs(start_with_only=bool(args.start_with)))
    return list(dict.fromkeys(normalize_ingredient(n) for n in names))


async def run_ingest(settings: Settings, drugs: list[str], mode: IngestMode) -> int:
    engine = create_engine(settings)
    failures = 0
    try:
        async with PoliteHttpClient(settings.contact_email) as http:
            products = await download_products(http, set(drugs))
            pipeline = IngestPipeline(
                create_session_factory(engine),
                DailyMedClient(http),
                db_size_limit_mb=settings.db_size_limit_mb,
            )
            for drug in drugs:
                if not any(p.ingredient_norm == drug for p in products):
                    log.warning("no_orange_book_products", ingredient=drug)
                    failures += 1
                    continue
                stats = await pipeline.ingest_drug(drug, products, mode)
                failures += 1 if stats.errors else 0
    finally:
        await engine.dispose()
    return failures


async def run_detect(settings: Settings, drugs: list[str], max_calls: int | None) -> int:
    engine = create_engine(settings)
    failures = 0
    try:
        sessions = create_session_factory(engine)
        llm = structured_llm(settings, "classify", sessions)
        if not llm.available:
            log.error(
                "no_llm_configured", hint="Set LLM_PROVIDER_ORDER, a key and a classify model"
            )
            return 1
        detector = EventDetector(sessions, llm, max_calls=max_calls)
        for drug in drugs:
            stats = await detector.detect_drug(drug)
            failures += 1 if stats.errors else 0
    finally:
        await engine.dispose()
    return failures


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = get_settings()
    configure_logging(settings.log_level, json=settings.env != "dev")
    if args.command == "detect":
        drugs = list(dict.fromkeys(normalize_ingredient(n) for n in args.drug))
        return 1 if asyncio.run(run_detect(settings, drugs, args.max_calls)) else 0
    if not settings.contact_email:
        log.error("contact_email_missing", hint="Set CONTACT_EMAIL for the DailyMed User-Agent")
        return 2
    drugs = resolve_drugs(args)
    failures = asyncio.run(run_ingest(settings, drugs, IngestMode(args.mode)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
