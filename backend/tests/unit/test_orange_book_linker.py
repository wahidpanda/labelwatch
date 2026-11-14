import io
import random
import zipfile
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from app.ingest.http import PoliteHttpClient
from app.ingest.linker import (
    assign_role,
    group_applications,
    is_likely_repackager,
    link_generics,
)
from app.ingest.orange_book import (
    EXPECTED_HEADER,
    OrangeBookFormatError,
    clean_strength,
    download_products,
    parse_products,
)

SAMPLE = Path(__file__).resolve().parents[1] / "fixtures" / "orange_book_products_sample.txt"


def _products(ingredients: set[str] | None = None):  # type: ignore[no-untyped-def]
    with SAMPLE.open(encoding="utf-8") as handle:
        return list(parse_products(handle, ingredients))


def test_parse_filters_by_normalised_ingredient() -> None:
    products = _products({"montelukast"})
    assert products
    assert {p.ingredient_norm for p in products} == {"montelukast"}
    singulair = [p for p in products if p.trade_name == "SINGULAIR"]
    assert {p.application_number for p in singulair} >= {"NDA020829", "NDA020830", "NDA021409"}
    assert all(p.is_rld for p in singulair)
    assert any(p.appl_type == "ANDA" for p in products)


def test_strength_annotations_are_removed() -> None:
    coumadin = [p for p in _products({"warfarin"}) if p.trade_name == "COUMADIN"]
    assert "1MG" in {p.strength for p in coumadin}
    assert all("**" not in p.strength for p in coumadin)
    assert clean_strength("5mg **note**") == "5MG"


def test_unexpected_header_is_rejected() -> None:
    with pytest.raises(OrangeBookFormatError, match="header"):
        list(parse_products(["Ingredient~Something"]))


@pytest.mark.parametrize(
    ("line", "message"),
    [
        ("A~B", "expected 14 fields"),
        ("WARFARIN SODIUM~TABLET;ORAL~X~Y~5MG~Z~000001~001~~d~No~No~RX~Y", "Appl_Type"),
    ],
)
def test_malformed_lines_are_rejected(line: str, message: str) -> None:
    with pytest.raises(OrangeBookFormatError, match=message):
        list(parse_products([EXPECTED_HEADER, line]))


def test_generics_link_to_the_rld_by_form_and_strength() -> None:
    groups = group_applications(_products({"montelukast", "warfarin"}))
    links = link_generics(groups)
    montelukast_andas = [
        g for g in groups.values() if g.appl_type == "ANDA" and g.ingredient_norm == "montelukast"
    ]
    assert montelukast_andas
    singulair = {"NDA020829", "NDA020830", "NDA021409"}
    for anda in montelukast_andas:
        link = links[anda.application_number]
        assert link.reference in singulair
        assert link.method == "orange_book_rld"
        assert Decimal("0") < link.confidence <= Decimal("1")
    warfarin_andas = [
        g for g in groups.values() if g.appl_type == "ANDA" and g.ingredient_norm == "warfarin"
    ]
    assert {links[g.application_number].reference for g in warfarin_andas} == {"NDA009218"}


def test_link_fallbacks_when_strength_or_form_differ() -> None:
    header = EXPECTED_HEADER
    rows = [
        "DRUGX~TABLET;ORAL~BRANDX~B CO~10MG~N~000001~001~~d~Yes~No~RX~B CO INC",
        "DRUGX~TABLET;ORAL~DRUGX~G1~20MG~A~000002~001~AB~d~No~No~RX~G1 INC",
        "DRUGX~CAPSULE;ORAL~DRUGX~G2~10MG~A~000003~001~AB~d~No~No~RX~G2 INC",
        "DRUGY~TABLET;ORAL~DRUGY~G3~10MG~A~000004~001~AB~d~No~No~RX~G3 INC",
    ]
    links = link_generics(group_applications(list(parse_products([header, *rows]))))
    assert links["ANDA000002"].method == "heuristic"
    assert links["ANDA000002"].confidence == Decimal("0.60")
    assert links["ANDA000003"].confidence == Decimal("0.40")
    assert "ANDA000004" not in links


@pytest.mark.parametrize(
    ("labeler", "expected"),
    [
        ("ORGANON LLC", False),
        ("Organon & Co.", False),
        ("PD-RX PHARMACEUTICALS, INC.", True),
        ("Physicians Total Care, Inc.", True),
        (None, False),
    ],
)
def test_repackager_heuristic(labeler: str | None, expected: bool) -> None:
    group = group_applications(_products({"montelukast"}))["NDA020829"]
    assert is_likely_repackager(labeler, group) is expected


def test_role_assignment() -> None:
    groups = group_applications(_products({"montelukast"}))
    brand = groups["NDA020829"]
    assert assign_role(brand, "SINGULAIR (MONTELUKAST SODIUM) TABLET [ORGANON LLC]") == "brand"
    assert assign_role(brand, "MONTELUKAST SODIUM TABLET [SOME AG CO]") == "authorized_generic"
    anda = next(g for g in groups.values() if g.appl_type == "ANDA")
    assert assign_role(anda, "MONTELUKAST SODIUM TABLET") == "generic"


async def test_download_products_streams_zip() -> None:
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("products.txt", SAMPLE.read_text(encoding="utf-8"))
        zf.writestr("patent.txt", "ignored")
    payload = archive.getvalue()

    async def no_sleep(seconds: float) -> None:
        return None

    transport = httpx.MockTransport(lambda r: httpx.Response(200, content=payload))
    async with PoliteHttpClient(
        "t@example.com", rps=1000, transport=transport, sleep=no_sleep, rng=random.Random(0)
    ) as http:
        products = await download_products(http, {"warfarin"})
    assert products
    assert {p.ingredient_norm for p in products} == {"warfarin"}

    empty = io.BytesIO()
    with zipfile.ZipFile(empty, "w") as zf:
        zf.writestr("other.txt", "x")
    bad = httpx.MockTransport(lambda r: httpx.Response(200, content=empty.getvalue()))
    async with PoliteHttpClient("t@example.com", rps=1000, transport=bad, sleep=no_sleep) as http:
        with pytest.raises(OrangeBookFormatError):
            await download_products(http, {"warfarin"})
