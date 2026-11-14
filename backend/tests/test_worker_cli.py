from datetime import date

import pytest

from app.ingest.pipeline import IngestMode, IngestStats, needs_sections
from app.worker.__main__ import build_parser, resolve_drugs


def test_parser_requires_a_drug_source() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["ingest"])


def test_resolve_drugs_normalises_and_dedupes() -> None:
    args = build_parser().parse_args(
        ["ingest", "--drug", "Warfarin Sodium", "--drug", "warfarin", "--drug", "Montelukast"]
    )
    assert resolve_drugs(args) == ["warfarin", "montelukast"]
    assert args.mode == "versions"


def test_resolve_drugs_from_start_with_seed() -> None:
    args = build_parser().parse_args(["ingest", "--start-with"])
    drugs = resolve_drugs(args)
    assert drugs
    assert all(d == d.lower() for d in drugs)


@pytest.mark.parametrize(
    ("role", "repack", "published", "mode", "expected"),
    [
        ("brand", False, date(2011, 12, 31), IngestMode.VERSIONS, False),
        ("brand", False, date(2012, 1, 1), IngestMode.VERSIONS, True),
        ("generic", False, date(2001, 1, 1), IngestMode.VERSIONS, True),
        ("generic", True, date(2020, 1, 1), IngestMode.VERSIONS, False),
        ("authorized_generic", False, date(2020, 1, 1), IngestMode.VERSIONS, False),
        ("generic", True, date(2020, 1, 1), IngestMode.FULL, True),
        ("brand", False, date(2020, 1, 1), IngestMode.METADATA, False),
    ],
)
def test_needs_sections(
    role: str, repack: bool, published: date, mode: IngestMode, expected: bool
) -> None:
    assert needs_sections(role, repack, published, mode) is expected


def test_stats_json_caps_errors() -> None:
    stats = IngestStats(errors=[f"e{i}" for i in range(60)])
    data = stats.as_json()
    assert len(data["errors"]) == 50
    assert data["error_count"] == 60
