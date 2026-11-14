"""FDA Orange Book products.txt importer. Format notes in docs/adr/0003."""

import io
import re
import tempfile
import zipfile
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from app.ingest.http import PoliteHttpClient
from app.ingest.normalize import normalize_ingredient, normalize_text

ORANGE_BOOK_URL = "https://www.fda.gov/media/76860/download"
EXPECTED_HEADER = (
    "Ingredient~DF;Route~Trade_Name~Applicant~Strength~Appl_Type~Appl_No~Product_No~TE_Code"
    "~Approval_Date~RLD~RS~Type~Applicant_Full_Name"
)
_APPL_TYPES = {"N": "NDA", "A": "ANDA", "B": "BLA"}
_ANNOTATION = re.compile(r"\*\*.*?\*\*")


class OrangeBookFormatError(ValueError):
    pass


@dataclass(frozen=True)
class OrangeBookProduct:
    ingredient: str
    ingredient_norm: str
    dosage_form_route: str
    trade_name: str
    applicant: str
    strength: str
    appl_type: str
    appl_no: str
    product_no: str
    te_code: str
    approval_date: str
    is_rld: bool
    is_rs: bool
    market_status: str
    applicant_full_name: str

    @property
    def application_number(self) -> str:
        return f"{self.appl_type}{self.appl_no}"

    @property
    def match_key(self) -> tuple[str, str, str]:
        return (self.ingredient_norm, self.dosage_form_route, self.strength)

    def as_json(self) -> dict[str, str | bool]:
        return {
            "product_no": self.product_no,
            "dosage_form_route": self.dosage_form_route,
            "strength": self.strength,
            "te_code": self.te_code,
            "approval_date": self.approval_date,
            "rld": self.is_rld,
            "rs": self.is_rs,
            "market_status": self.market_status,
        }


def clean_strength(value: str) -> str:
    return normalize_text(_ANNOTATION.sub("", value)).upper()


def parse_products(
    lines: Iterable[str], ingredients: set[str] | None = None
) -> Iterator[OrangeBookProduct]:
    """Parse products.txt lines; keep single-ingredient products in `ingredients` if given."""
    iterator = iter(lines)
    header = next(iterator, "").strip().lstrip("\ufeff")
    if header != EXPECTED_HEADER:
        raise OrangeBookFormatError(f"Unexpected Orange Book header: {header[:120]!r}")
    for line_no, raw in enumerate(iterator, start=2):
        line = raw.rstrip("\r\n")
        if not line:
            continue
        fields = line.split("~")
        if len(fields) != 14:
            raise OrangeBookFormatError(f"Line {line_no}: expected 14 fields, got {len(fields)}")
        ingredient_norm = normalize_ingredient(fields[0])
        if ingredients is not None and ingredient_norm not in ingredients:
            continue
        appl_type = _APPL_TYPES.get(fields[5].strip())
        if appl_type is None:
            raise OrangeBookFormatError(f"Line {line_no}: unknown Appl_Type {fields[5]!r}")
        yield OrangeBookProduct(
            ingredient=normalize_text(fields[0]),
            ingredient_norm=ingredient_norm,
            dosage_form_route=normalize_text(fields[1]).upper(),
            trade_name=normalize_text(fields[2]),
            applicant=normalize_text(fields[3]),
            strength=clean_strength(fields[4]),
            appl_type=appl_type,
            appl_no=fields[6].strip().zfill(6),
            product_no=fields[7].strip(),
            te_code=fields[8].strip(),
            approval_date=fields[9].strip(),
            is_rld=fields[10].strip().lower() == "yes",
            is_rs=fields[11].strip().lower() == "yes",
            market_status=fields[12].strip(),
            applicant_full_name=normalize_text(fields[13]),
        )


async def download_products(
    http: PoliteHttpClient, ingredients: set[str]
) -> list[OrangeBookProduct]:
    """Stream the Orange Book ZIP and return products for the given normalised ingredients."""
    with tempfile.SpooledTemporaryFile(max_size=4 * 1024 * 1024) as buffer:
        async with http.stream(ORANGE_BOOK_URL) as response:
            async for chunk in response.aiter_bytes():
                buffer.write(chunk)
        buffer.seek(0)
        try:
            with zipfile.ZipFile(buffer) as archive, archive.open("products.txt") as raw:
                text = io.TextIOWrapper(raw, encoding="utf-8", errors="replace")
                return list(parse_products(text, ingredients))
        except (zipfile.BadZipFile, KeyError) as exc:
            raise OrangeBookFormatError("Orange Book archive missing products.txt") from exc
