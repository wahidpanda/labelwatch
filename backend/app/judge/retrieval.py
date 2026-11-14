"""Candidate retrieval in generic labels and quote verification (SPEC section 8, D and F)."""

import re
from dataclasses import dataclass

from rank_bm25 import BM25Okapi
from rapidfuzz import fuzz

from app.ingest.normalize import hash_form

TOP_K = 5
EXACT_THRESHOLD = 0.97
LEXICAL_FLOOR = 0.35
QUOTE_THRESHOLD = 0.95
_TOKEN = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class ScoredUnit:
    text: str
    score: float
    exact: float


def tokens(text: str) -> list[str]:
    return _TOKEN.findall(hash_form(text))


def rank_units(brand_unit: str, units: list[str], k: int = TOP_K) -> list[ScoredUnit]:
    """Blend of BM25 (normalised to the best hit) and fuzzy token overlap, highest first."""
    if not units:
        return []
    query = tokens(brand_unit)
    bm25 = BM25Okapi([tokens(u) or ["_"] for u in units]).get_scores(query)
    best = max(float(max(bm25)), 0.0)
    target = hash_form(brand_unit)
    scored = []
    for unit, raw in zip(units, bm25, strict=True):
        form = hash_form(unit)
        lexical = max(float(raw), 0.0) / best if best > 0 else 0.0
        overlap = fuzz.token_set_ratio(target, form) / 100.0
        exact = fuzz.ratio(target, form) / 100.0
        scored.append(ScoredUnit(unit, round(0.5 * lexical + 0.5 * overlap, 4), exact))
    scored.sort(key=lambda s: s.score, reverse=True)
    return scored[:k]


def quote_is_verbatim(quote: str, units: list[str]) -> bool:
    form = hash_form(quote)
    if not form:
        return False
    for unit in units:
        unit_form = hash_form(unit)
        if form in unit_form or fuzz.partial_ratio(form, unit_form) / 100.0 >= QUOTE_THRESHOLD:
            return True
    return False


def verify_quotes(quotes: list[str], units: list[str]) -> bool:
    return bool(quotes) and all(quote_is_verbatim(q, units) for q in quotes)
