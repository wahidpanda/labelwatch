import pytest

from app.ingest.normalize import (
    hash_form,
    join_units,
    normalize_ingredient,
    normalize_text,
    split_units,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Montelukast Sodium", "montelukast"),
        ("ZOLPIDEM TARTRATE", "zolpidem"),
        ("Clopidogrel Bisulfate", "clopidogrel"),
        ("Escitalopram Oxalate", "escitalopram"),
        ("Levothyroxine Sodium Anhydrous", "levothyroxine"),
        ("Tramadol HCl", "tramadol"),
        ("warfarin", "warfarin"),
        ("Sodium", "sodium"),
    ],
)
def test_normalize_ingredient_strips_salts(raw: str, expected: str) -> None:
    assert normalize_ingredient(raw) == expected


def test_normalize_text_nfkc_and_whitespace() -> None:
    assert normalize_text("  ﬁve\u00a0 mg\n\tdaily  ") == "five mg daily"
    assert hash_form("Do NOT  Use") == "do not use"


def test_units_round_trip() -> None:
    units = ["one", "two"]
    assert split_units(join_units(units)) == units
    assert split_units("") == []
