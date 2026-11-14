import io
import uuid
from datetime import date
from pathlib import Path

from app.ingest.spl_parser import parse_spl

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "spl"


def _parse_fixture(name: str):  # type: ignore[no-untyped-def]
    with (FIXTURES / name).open("rb") as handle:
        return parse_spl(handle)


def _doc(body: str) -> io.BytesIO:
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<document xmlns="urn:hl7-org:v3">
  <setId root="11111111-2222-3333-4444-555555555555"/>
  <versionNumber value="7"/>
  <effectiveTime value="20240102"/>
  <title>Test <sup>label</sup></title>
  <component><structuredBody>{body}</structuredBody></component>
</document>"""
    return io.BytesIO(xml.encode("utf-8"))


def _section(code: str, inner: str) -> str:
    return f'<component><section><code code="{code}"/><title>T</title><text>{inner}</text></section></component>'


def test_plr_label_extracts_all_safety_sections() -> None:
    spl = _parse_fixture("singulair_plr_v5.xml")
    assert spl.setid == uuid.UUID("482dcc92-b47f-4ea6-854a-f5ac2aea7842")
    assert spl.version == 5
    assert spl.effective_date == date(2025, 4, 30)
    assert {"NDA020829", "NDA020830", "NDA021409"} <= spl.approvals
    assert set(spl.sections) >= {
        "boxed_warning",
        "warnings_precautions",
        "adverse_reactions",
        "contraindications",
        "drug_interactions",
        "specific_populations",
        "pregnancy",
    }
    assert "neuropsychiatric" in spl.sections["boxed_warning"].body.lower()
    assert spl.sections["boxed_warning"].loinc == "34066-1"


def test_plr_pregnancy_text_is_not_duplicated_in_specific_populations() -> None:
    spl = _parse_fixture("singulair_plr_v5.xml")
    pregnancy = set(spl.sections["pregnancy"].units)
    populations = set(spl.sections["specific_populations"].units)
    shared = {u for u in pregnancy & populations if len(u) > 40}
    assert shared == set()


def test_old_format_label_uses_precautions_and_no_plr_sections() -> None:
    spl = _parse_fixture("singulair_old_format_2010.xml")
    assert spl.version == 1
    assert spl.effective_date == date(2010, 3, 1)
    assert "precautions" in spl.sections
    assert "adverse_reactions" in spl.sections
    assert "warnings_precautions" not in spl.sections
    # Pregnancy is a title-only heading here; its text sits in a sibling subsection.
    assert "pregnancy" not in spl.sections
    assert any(
        "teratogenic" in u.lower() or "pregnan" in u.lower()
        for u in spl.sections["precautions"].units
    )


def test_units_are_paragraphs_items_and_rows() -> None:
    body = _section(
        "34084-4",
        "<paragraph>First  paragraph\n with   spaces.</paragraph>"
        "<list><item>Item one</item><item><paragraph>Nested para</paragraph></item></list>"
        "<table><tbody><tr><td>Headache</td><td><paragraph>18%</paragraph></td></tr></tbody></table>",
    )
    spl = parse_spl(_doc(body))
    assert spl.sections["adverse_reactions"].units == (
        "First paragraph with spaces.",
        "Item one",
        "Nested para",
        "Headache | 18%",
    )
    assert spl.setid == uuid.UUID("11111111-2222-3333-4444-555555555555")
    assert spl.version == 7
    assert spl.title == "Test label"


def test_highlights_excerpts_and_titles_are_skipped() -> None:
    body = _section(
        "34066-1",
        "<paragraph>Real boxed text.</paragraph>",
    ).replace(
        "<text>",
        "<excerpt><highlight><text><paragraph>Highlight copy</paragraph></text></highlight></excerpt><text>",
    )
    spl = parse_spl(_doc(body))
    assert spl.sections["boxed_warning"].units == ("Real boxed text.",)


def test_nested_safety_section_is_extracted_separately() -> None:
    inner = '<component><section><code code="42228-7"/><text><paragraph>Pregnancy text</paragraph></text></section></component>'
    outer = (
        '<component><section><code code="43684-0"/><text><paragraph>Populations text</paragraph></text>'
        f"{inner}</section></component>"
    )
    spl = parse_spl(_doc(outer))
    assert spl.sections["specific_populations"].units == ("Populations text",)
    assert spl.sections["pregnancy"].units == ("Pregnancy text",)


def test_repeated_section_codes_are_joined_and_empty_sections_dropped() -> None:
    body = (
        _section("34084-4", "<paragraph>Product A reaction</paragraph>")
        + _section("34084-4", "<paragraph>Product B reaction</paragraph>")
        + _section("34070-3", "")
    )
    spl = parse_spl(_doc(body))
    assert spl.sections["adverse_reactions"].units == ("Product A reaction", "Product B reaction")
    assert "contraindications" not in spl.sections


def test_inline_markup_and_line_breaks_become_text() -> None:
    body = _section(
        "34070-3",
        '<paragraph>Do <content styleCode="bold">not</content> use<br/>with MAOIs.</paragraph>',
    )
    spl = parse_spl(_doc(body))
    assert spl.sections["contraindications"].units == ("Do not use with MAOIs.",)


def test_external_entities_are_not_resolved() -> None:
    xml = b"""<?xml version="1.0"?>
<!DOCTYPE document [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
<document xmlns="urn:hl7-org:v3"><component><structuredBody>
<component><section><code code="34070-3"/><text><paragraph>a &xxe; b</paragraph></text></section></component>
</structuredBody></component></document>"""
    spl = parse_spl(io.BytesIO(xml))
    assert "root:" not in spl.sections["contraindications"].body


def test_missing_metadata_is_tolerated() -> None:
    xml = b'<document xmlns="urn:hl7-org:v3"><effectiveTime value="bad"/></document>'
    spl = parse_spl(io.BytesIO(xml))
    assert spl.setid is None
    assert spl.version is None
    assert spl.effective_date is None
    assert spl.sections == {}
