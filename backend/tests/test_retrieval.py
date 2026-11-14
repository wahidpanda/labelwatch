from app.judge.retrieval import quote_is_verbatim, rank_units, verify_quotes

BRAND = "Serious neuropsychiatric events, including suicidal thinking, have been reported."
UNITS = [
    "Take with or without food.",
    "Neuropsychiatric events, including suicidal thinking and behavior, have been reported.",
    "Store at room temperature.",
]


def test_rank_puts_matching_unit_first() -> None:
    ranked = rank_units(BRAND, UNITS)
    assert ranked[0].text == UNITS[1]
    assert ranked[0].score > 0.5
    assert ranked[-1].score < ranked[0].score


def test_rank_empty_and_k() -> None:
    assert rank_units(BRAND, []) == []
    assert len(rank_units(BRAND, UNITS, k=2)) == 2


def test_exact_score_detects_near_identical_text() -> None:
    ranked = rank_units(BRAND, [BRAND.upper(), "Unrelated."])
    assert ranked[0].exact == 1.0


def test_quotes_must_appear_in_units() -> None:
    assert quote_is_verbatim("suicidal thinking and behavior", UNITS)
    assert quote_is_verbatim(
        "Neuropsychiatric events, including suicidal thinking and behaviour", UNITS
    )
    assert not quote_is_verbatim("may cause liver failure", UNITS)
    assert not quote_is_verbatim("   ", UNITS)
    assert verify_quotes(["Store at room temperature."], UNITS)
    assert not verify_quotes([], UNITS)
    assert not verify_quotes(["Store at room temperature.", "invented sentence here"], UNITS)
