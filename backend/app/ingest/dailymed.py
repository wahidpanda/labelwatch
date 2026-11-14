"""DailyMed REST v2 client. Field formats are documented in docs/adr/0003."""

import hashlib
import re
import tempfile
import uuid
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from app.ingest.http import PoliteHttpClient
from app.ingest.spl_parser import ParsedSpl, parse_spl

BASE_URL = "https://dailymed.nlm.nih.gov/dailymed"
API_URL = f"{BASE_URL}/services/v2"
PAGE_SIZE = 100
_MAX_ZIP_BYTES = 50 * 1024 * 1024
_LABELER = re.compile(r"\[([^\[\]]+)\]\s*$")


class DailyMedFormatError(ValueError):
    pass


@dataclass(frozen=True)
class SetSummary:
    setid: uuid.UUID
    title: str
    version: int
    published_date: date

    @property
    def labeler(self) -> str | None:
        return parse_labeler(self.title)


@dataclass(frozen=True)
class VersionInfo:
    version: int
    published_date: date


@dataclass(frozen=True)
class FetchedVersion:
    parsed: ParsedSpl
    source_url: str
    zip_sha256: str


def parse_published_date(value: str) -> date:
    return datetime.strptime(value.strip(), "%b %d, %Y").date()


def parse_labeler(title: str) -> str | None:
    match = _LABELER.search(title)
    return match.group(1).strip() if match else None


def version_zip_url(setid: uuid.UUID, version: int) -> str:
    return f"{BASE_URL}/getFile.cfm?type=zip&setid={setid}&version={version}"


def _set_summary(item: dict[str, Any]) -> SetSummary:
    try:
        return SetSummary(
            setid=uuid.UUID(str(item["setid"])),
            title=str(item["title"]),
            version=int(item["spl_version"]),
            published_date=parse_published_date(str(item["published_date"])),
        )
    except (KeyError, ValueError) as exc:
        raise DailyMedFormatError(f"Unexpected spls item: {item!r}") from exc


class DailyMedClient:
    def __init__(self, http: PoliteHttpClient) -> None:
        self._http = http

    async def list_sets(
        self, *, application_number: str | None = None, drug_name: str | None = None
    ) -> list[SetSummary]:
        if not application_number and not drug_name:
            raise ValueError("Give application_number or drug_name")
        params: dict[str, Any] = {"pagesize": PAGE_SIZE, "page": 1}
        if application_number:
            params["application_number"] = application_number
        if drug_name:
            params["drug_name"] = drug_name
        results: list[SetSummary] = []
        while True:
            payload = await self._http.get_json(f"{API_URL}/spls.json", params=params)
            results.extend(_set_summary(item) for item in payload.get("data") or [])
            total_pages = int(payload.get("metadata", {}).get("total_pages") or 1)
            if params["page"] >= total_pages:
                return results
            params["page"] += 1

    async def history(self, setid: uuid.UUID) -> list[VersionInfo]:
        payload = await self._http.get_json(f"{API_URL}/spls/{setid}/history.json")
        data = payload.get("data")
        entries = data.get("history") if isinstance(data, dict) else None
        if not isinstance(entries, list):
            raise DailyMedFormatError(f"Unexpected history payload for {setid}")
        versions = {
            int(e["spl_version"]): parse_published_date(str(e["published_date"])) for e in entries
        }
        return [VersionInfo(v, d) for v, d in sorted(versions.items())]

    async def fetch_version(self, setid: uuid.UUID, version: int) -> FetchedVersion:
        url = version_zip_url(setid, version)
        digest = hashlib.sha256()
        with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024) as buffer:
            size = 0
            async with self._http.stream(url) as response:
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > _MAX_ZIP_BYTES:
                        raise DailyMedFormatError(f"SPL archive too large for {setid} v{version}")
                    digest.update(chunk)
                    buffer.write(chunk)
            buffer.seek(0)
            try:
                with zipfile.ZipFile(buffer) as archive:
                    names = [n for n in archive.namelist() if n.lower().endswith(".xml")]
                    if not names:
                        raise DailyMedFormatError(f"No SPL XML in archive {setid} v{version}")
                    with archive.open(names[0]) as xml_stream:
                        parsed = parse_spl(xml_stream)
            except zipfile.BadZipFile as exc:
                raise DailyMedFormatError(f"Not a ZIP for {setid} v{version}") from exc
        return FetchedVersion(parsed=parsed, source_url=url, zip_sha256=digest.hexdigest())
