"""Group Orange Book products into applications, link ANDAs to their RLD, assign set roles."""

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from app.ingest.orange_book import OrangeBookProduct

_WORD = re.compile(r"[a-z0-9]+")
# Corporate filler words that do not identify a company.
_STOP_WORDS = frozenset(
    {
        "inc",
        "llc",
        "ltd",
        "limited",
        "co",
        "corp",
        "corporation",
        "company",
        "pharma",
        "pharmaceutical",
        "pharmaceuticals",
        "pharms",
        "pharm",
        "labs",
        "laboratories",
        "laboratory",
        "usa",
        "us",
        "the",
        "and",
        "of",
        "a",
        "sub",
        "division",
        "lp",
        "plc",
        "gmbh",
        "sa",
        "ag",
        "rx",
        "health",
        "healthcare",
    }
)


@dataclass
class ApplicationGroup:
    appl_type: str
    appl_no: str
    ingredient_norm: str
    applicant: str
    applicant_full_name: str
    trade_name: str
    products: list[OrangeBookProduct] = field(default_factory=list)

    @property
    def application_number(self) -> str:
        return f"{self.appl_type}{self.appl_no}"

    @property
    def is_rld(self) -> bool:
        return any(p.is_rld for p in self.products)


@dataclass(frozen=True)
class Link:
    reference: str
    method: str
    confidence: Decimal


def group_applications(products: list[OrangeBookProduct]) -> dict[str, ApplicationGroup]:
    groups: dict[str, ApplicationGroup] = {}
    for product in products:
        group = groups.get(product.application_number)
        if group is None:
            group = ApplicationGroup(
                appl_type=product.appl_type,
                appl_no=product.appl_no,
                ingredient_norm=product.ingredient_norm,
                applicant=product.applicant,
                applicant_full_name=product.applicant_full_name,
                trade_name=product.trade_name,
            )
            groups[product.application_number] = group
        group.products.append(product)
    return groups


def link_generics(groups: dict[str, ApplicationGroup]) -> dict[str, Link]:
    """Map each ANDA application number to the RLD application it references."""
    rld_by_key: dict[tuple[str, str, str], str] = {}
    rld_by_form: dict[tuple[str, str], set[str]] = defaultdict(set)
    rld_by_ingredient: dict[str, set[str]] = defaultdict(set)
    for group in groups.values():
        if group.appl_type == "ANDA":
            continue
        for product in group.products:
            if product.is_rld:
                rld_by_key[product.match_key] = group.application_number
                rld_by_form[(product.ingredient_norm, product.dosage_form_route)].add(
                    group.application_number
                )
                rld_by_ingredient[product.ingredient_norm].add(group.application_number)

    links: dict[str, Link] = {}
    for group in groups.values():
        if group.appl_type != "ANDA":
            continue
        exact = Counter(
            rld_by_key[p.match_key] for p in group.products if p.match_key in rld_by_key
        )
        if exact:
            reference, matched = exact.most_common(1)[0]
            confidence = Decimal(matched) / Decimal(len(group.products))
            links[group.application_number] = Link(
                reference, "orange_book_rld", confidence.quantize(Decimal("0.01"))
            )
            continue
        by_form = Counter(
            ref
            for p in group.products
            for ref in rld_by_form.get((p.ingredient_norm, p.dosage_form_route), set())
        )
        if by_form:
            links[group.application_number] = Link(
                by_form.most_common(1)[0][0], "heuristic", Decimal("0.60")
            )
            continue
        candidates = sorted(rld_by_ingredient.get(group.ingredient_norm, set()))
        if candidates:
            links[group.application_number] = Link(candidates[0], "heuristic", Decimal("0.40"))
    return links


def _company_words(name: str | None) -> set[str]:
    return {w for w in _WORD.findall((name or "").lower()) if w not in _STOP_WORDS and len(w) > 1}


def is_likely_repackager(labeler: str | None, group: ApplicationGroup) -> bool:
    """True when the label's labeler shares no identifying word with the application holder."""
    labeler_words = _company_words(labeler)
    if not labeler_words:
        return False
    holder_words = _company_words(group.applicant) | _company_words(group.applicant_full_name)
    return not (labeler_words & holder_words)


def assign_role(group: ApplicationGroup, set_title: str) -> str:
    if group.appl_type == "ANDA":
        return "generic"
    if group.is_rld:
        trade = group.trade_name.lower()
        if trade and trade in set_title.lower():
            return "brand"
        return "authorized_generic"
    return "authorized_generic" if group.appl_type == "NDA" else "other"
