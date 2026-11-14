"""Leaflet text extraction: embedded PDF text first, a vision model for photos and scans."""

import base64
import hashlib
import io
from dataclasses import dataclass, field
from typing import Any, Literal

import pypdfium2 as pdfium  # type: ignore[import-untyped]
from PIL import Image, ImageOps, UnidentifiedImageError

from app.errors import AppError
from app.llm.factory import StructuredLLM
from app.llm.prompts import OCR_SYSTEM
from app.llm.schemas import OcrOut

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_PAGES = 6
MAX_IMAGE_SIDE = 2000
# A digital PDF has real text; fewer characters than this means a scan.
MIN_PDF_TEXT_CHARS = 200
IMAGE_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
PDF_TYPE = "application/pdf"

Source = Literal["pdf_text", "vision"]


@dataclass(frozen=True)
class Extraction:
    text: str
    source: Source
    pages: int
    sha256: str
    language: str = "en"
    legible: bool = True
    unclear_parts: list[str] = field(default_factory=list)
    provider: str | None = None
    model: str | None = None


def sniff_type(data: bytes) -> str | None:
    if data.startswith(b"%PDF"):
        return PDF_TYPE
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def pdf_text(data: bytes) -> tuple[str, int]:
    pdf = pdfium.PdfDocument(data)
    try:
        pages = [pdf[i].get_textpage().get_text_range() for i in range(len(pdf))]
        return "\n".join(p.strip() for p in pages if p.strip()), len(pdf)
    finally:
        pdf.close()


def pdf_page_images(data: bytes) -> list[bytes]:
    pdf = pdfium.PdfDocument(data)
    try:
        images = []
        for i in range(min(len(pdf), MAX_PAGES)):
            bitmap = pdf[i].render(scale=2.0)
            images.append(_jpeg(bitmap.to_pil()))
        return images
    finally:
        pdf.close()


def prepare_image(data: bytes) -> bytes:
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise AppError(422, "The image could not be read. Upload a JPEG, PNG or WebP.") from exc
    return _jpeg(ImageOps.exif_transpose(image))


def _jpeg(image: Image.Image) -> bytes:
    image = image.convert("RGB")
    image.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()


def vision_content(images: list[bytes]) -> list[str | dict[str, Any]]:
    blocks: list[str | dict[str, Any]] = [
        {"type": "text", "text": f"Transcribe this leaflet ({len(images)} page image(s))."}
    ]
    for image in images:
        encoded = base64.b64encode(image).decode("ascii")
        blocks.append({"type": "image", "base64": encoded, "mime_type": "image/jpeg"})
    return blocks


async def extract(data: bytes, content_type: str, llm: StructuredLLM) -> Extraction:
    if not data:
        raise AppError(422, "The file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise AppError(413, "The file is larger than 8 MB.")
    digest = sha256_of(data)
    if content_type == PDF_TYPE:
        try:
            text, pages = pdf_text(data)
            images = [] if len(text) >= MIN_PDF_TEXT_CHARS else pdf_page_images(data)
        except pdfium.PdfiumError as exc:
            raise AppError(422, "The PDF could not be opened.") from exc
        if not images:
            return Extraction(text=text, source="pdf_text", pages=pages, sha256=digest)
    elif content_type in IMAGE_TYPES:
        images, pages = [prepare_image(data)], 1
    else:
        raise AppError(415, "Upload a PDF, JPEG, PNG or WebP file.")
    result = await llm.invoke(
        OcrOut, OCR_SYSTEM, vision_content(images), metadata={"feature": "leaflet_ocr"}
    )
    out = result.output
    return Extraction(
        text=out.text.strip(),
        source="vision",
        pages=pages,
        sha256=digest,
        language=out.language,
        legible=out.legible,
        unclear_parts=out.unclear_parts,
        provider=result.provider,
        model=result.model,
    )
