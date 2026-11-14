import io
import os
import random
import uuid
import zipfile
from datetime import date
from pathlib import Path

import httpx
import pytest
import vcr

from app.ingest.dailymed import (
    DailyMedClient,
    DailyMedFormatError,
    parse_labeler,
    parse_published_date,
    version_zip_url,
)
from app.ingest.http import PoliteHttpClient

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
CASSETTES = FIXTURES / "cassettes"
SINGULAIR_SET = uuid.UUID("482dcc92-b47f-4ea6-854a-f5ac2aea7842")

recorder = vcr.VCR(
    cassette_library_dir=str(CASSETTES),
    record_mode="once" if os.environ.get("VCR_RECORD") else "none",
    match_on=["method", "scheme", "host", "path", "query"],
    filter_headers=["user-agent"],
)


async def _noop_sleep(seconds: float) -> None:
    return None


def _client(transport: httpx.AsyncBaseTransport | None = None) -> PoliteHttpClient:
    return PoliteHttpClient(
        "test@example.com", rps=1000, transport=transport, sleep=_noop_sleep, rng=random.Random(0)
    )


def test_date_and_labeler_parsing() -> None:
    assert parse_published_date("Oct 30, 2026") == date(2026, 10, 30)
    assert parse_labeler("MONTELUKAST SODIUM TABLET [AUROBINDO PHARMA LIMITED]") == (
        "AUROBINDO PHARMA LIMITED"
    )
    assert parse_labeler("No labeler here") is None


async def test_list_sets_by_application_number() -> None:
    with recorder.use_cassette("dailymed_sets_by_application.yaml"):
        async with _client() as http:
            sets = await DailyMedClient(http).list_sets(application_number="NDA020829")
    by_id = {s.setid: s for s in sets}
    assert SINGULAIR_SET in by_id
    assert by_id[SINGULAIR_SET].labeler == "ORGANON LLC"
    assert all(s.version >= 1 for s in sets)


async def test_history_returns_sorted_versions() -> None:
    with recorder.use_cassette("dailymed_history_singulair.yaml"):
        async with _client() as http:
            versions = await DailyMedClient(http).history(SINGULAIR_SET)
    numbers = [v.version for v in versions]
    assert numbers == sorted(numbers)
    assert numbers[-1] >= 5
    assert all(isinstance(v.published_date, date) for v in versions)


async def test_list_sets_follows_pagination() -> None:
    pages = {
        "1": {"metadata": {"total_pages": 2}, "data": [_item("a" * 8, 1)]},
        "2": {"metadata": {"total_pages": 2}, "data": [_item("b" * 8, 2)]},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=pages[request.url.params["page"]])

    async with _client(httpx.MockTransport(handler)) as http:
        sets = await DailyMedClient(http).list_sets(drug_name="montelukast")
    assert [s.version for s in sets] == [1, 2]


async def test_list_sets_requires_a_filter() -> None:
    async with _client() as http:
        with pytest.raises(ValueError, match="application_number or drug_name"):
            await DailyMedClient(http).list_sets()


async def test_malformed_payloads_raise_format_errors() -> None:
    bad = {"metadata": {}, "data": [{"setid": "not-a-uuid"}]}
    async with _client(httpx.MockTransport(lambda r: httpx.Response(200, json=bad))) as http:
        with pytest.raises(DailyMedFormatError):
            await DailyMedClient(http).list_sets(drug_name="x")
    history_bad: dict[str, list[object]] = {"data": []}
    async with _client(httpx.MockTransport(lambda r: httpx.Response(200, json=history_bad))) as h:
        with pytest.raises(DailyMedFormatError):
            await DailyMedClient(h).history(SINGULAIR_SET)


async def test_fetch_version_reads_only_the_xml_from_the_zip() -> None:
    xml = (FIXTURES / "spl" / "singulair_plr_v5.xml").read_bytes()
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("label-01.jpg", b"\xff\xd8" + b"0" * 1000)
        zf.writestr("482dcc92.xml", xml)
    payload = archive.getvalue()
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, content=payload, headers={"Content-Type": "application/zip"})

    async with _client(httpx.MockTransport(handler)) as http:
        fetched = await DailyMedClient(http).fetch_version(SINGULAIR_SET, 5)
    assert seen == [version_zip_url(SINGULAIR_SET, 5)]
    assert fetched.parsed.version == 5
    assert "boxed_warning" in fetched.parsed.sections
    assert len(fetched.zip_sha256) == 64


@pytest.mark.parametrize("content", [b"not a zip", b""])
async def test_fetch_version_rejects_non_zip(content: bytes) -> None:
    async with _client(httpx.MockTransport(lambda r: httpx.Response(200, content=content))) as h:
        with pytest.raises(DailyMedFormatError):
            await DailyMedClient(h).fetch_version(SINGULAIR_SET, 1)


async def test_fetch_version_rejects_zip_without_xml() -> None:
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("only.jpg", b"x")
    data = archive.getvalue()
    async with _client(httpx.MockTransport(lambda r: httpx.Response(200, content=data))) as h:
        with pytest.raises(DailyMedFormatError, match="No SPL XML"):
            await DailyMedClient(h).fetch_version(SINGULAIR_SET, 1)


def _item(prefix: str, version: int) -> dict[str, object]:
    return {
        "setid": f"{prefix}-0000-0000-0000-000000000000",
        "title": "X [LAB]",
        "spl_version": version,
        "published_date": "Jan 02, 2024",
    }
