"""Minimal grounded chat: tool-free overview answers until LangGraph WP-6 is expanded."""

import json
import uuid
from collections.abc import AsyncIterator

from app.errors import AppError
from app.services.catalog import CatalogService


async def stream_answer(service: CatalogService, question: str) -> AsyncIterator[str]:
    q = question.strip()
    if not q:
        raise AppError(422, "Question is required.")
    if any(x in q.lower() for x in ("dose", "dosage", "should i take", "চিকিৎসা")):
        text = "I cannot give medical advice. Ask a pharmacist or doctor."
    else:
        overview = await service.overview()
        text = (
            f"This tool tracks US generic label lag using DailyMed publication dates. "
            f"Right now we track {overview.drugs} medicines, {overview.events} safety changes, "
            f"and {overview.judgements} judgements. "
            f"Median lag {overview.median_lag_days or 'n/a'} days. "
            f"Not medical advice."
        )
    yield _sse({"type": "step", "name": "overview", "status": "done"})
    for word in text.split():
        yield _sse({"type": "token", "text": word + " "})
    yield _sse({"type": "spoken_summary", "text": text[:160]})
    yield _sse({"type": "done", "session_id": str(uuid.uuid4())})


def _sse(payload: dict[str, object]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
