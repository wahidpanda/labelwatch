"""Stream-parse an SPL XML document into safety sections made of text units."""

import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date
from typing import IO

from lxml import etree

from app.ingest.normalize import join_units, normalize_text

NS = "urn:hl7-org:v3"
_Q = f"{{{NS}}}"

SAFETY_SECTIONS: dict[str, str] = {
    "34066-1": "boxed_warning",
    "43685-7": "warnings_precautions",
    "34071-1": "warnings",
    "42232-9": "precautions",
    "34084-4": "adverse_reactions",
    "34070-3": "contraindications",
    "34073-7": "drug_interactions",
    "43684-0": "specific_populations",
    "42228-7": "pregnancy",
}
_UNIT_TAGS = frozenset({"paragraph", "item"})
_BLOCK_TAGS = frozenset({"paragraph", "item", "list", "table", "section", "component"})
_SKIP_TAGS = frozenset({"excerpt", "renderMultiMedia", "observationMedia"})


@dataclass(frozen=True)
class ParsedSection:
    key: str
    loinc: str
    units: tuple[str, ...]

    @property
    def body(self) -> str:
        return join_units(self.units)


@dataclass
class ParsedSpl:
    setid: uuid.UUID | None = None
    version: int | None = None
    effective_date: date | None = None
    title: str = ""
    approvals: set[str] = field(default_factory=set)
    sections: dict[str, ParsedSection] = field(default_factory=dict)


def _local(tag: object) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _section_code(section: etree._Element) -> str | None:
    code = section.find(f"{_Q}code")
    return None if code is None else code.get("code")


def _inline_text(element: etree._Element) -> str:
    """Text of an element, excluding nested block elements but keeping their tails."""
    parts: list[str] = [element.text or ""]
    for child in element:
        tag = _local(child.tag)
        if tag in _BLOCK_TAGS or tag in _SKIP_TAGS:
            pass
        elif tag == "br":
            parts.append(" ")
        else:
            parts.append(_inline_text(child))
        parts.append(child.tail or "")
    return "".join(parts)


def _all_text(element: etree._Element) -> str:
    return "".join(str(part) for part in element.itertext())


def _row_text(row: etree._Element) -> str:
    cells = [normalize_text(_all_text(cell)) for cell in row if _local(cell.tag) in ("td", "th")]
    return " | ".join(c for c in cells if c)


def _units(element: etree._Element) -> Iterator[str]:
    for child in element:
        tag = _local(child.tag)
        if tag in _SKIP_TAGS or tag == "title":
            continue
        if tag == "section" and _section_code(child) in SAFETY_SECTIONS:
            continue  # nested safety section is extracted on its own
        if tag == "tr":
            row = _row_text(child)
            if row:
                yield row
            continue
        if tag in _UNIT_TAGS:
            own = normalize_text(_inline_text(child))
            if own:
                yield own
        yield from _units(child)


def _parse_date(value: str | None) -> date | None:
    if not value or len(value) < 8 or not value[:8].isdigit():
        return None
    return date(int(value[:4]), int(value[4:6]), int(value[6:8]))


def parse_spl(source: IO[bytes]) -> ParsedSpl:
    result = ParsedSpl()
    collected: dict[str, tuple[str, list[str]]] = {}
    context = etree.iterparse(
        source,
        events=("end",),
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        huge_tree=False,
    )
    for _, element in context:
        tag = _local(element.tag)
        parent = element.getparent()
        parent_tag = _local(parent.tag) if parent is not None else ""
        if parent_tag == "document":
            if tag == "setId" and element.get("root"):
                result.setid = uuid.UUID(element.get("root", ""))
            elif tag == "versionNumber" and element.get("value", "").isdigit():
                result.version = int(element.get("value", "0"))
            elif tag == "effectiveTime":
                result.effective_date = _parse_date(element.get("value"))
            elif tag == "title":
                result.title = normalize_text(_all_text(element))
        elif tag == "id" and parent_tag == "approval" and element.get("extension"):
            result.approvals.add(element.get("extension", "").strip().upper())
        elif tag == "section":
            code = _section_code(element)
            if code in SAFETY_SECTIONS:
                key = SAFETY_SECTIONS[code]
                _, units = collected.setdefault(key, (code, []))
                units.extend(_units(element))
            if not any(
                _section_code(a) in SAFETY_SECTIONS for a in element.iterancestors(f"{_Q}section")
            ):
                element.clear(keep_tail=True)
    result.sections = {
        key: ParsedSection(key=key, loinc=code, units=tuple(units))
        for key, (code, units) in collected.items()
        if units
    }
    return result
