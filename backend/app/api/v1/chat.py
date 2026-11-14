from typing import Annotated

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.assistant.chat import stream_answer
from app.db.models import ChatFeedback
from app.deps import CatalogServiceDep, SessionDep

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatIn(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    locale: str = Field(default="en", pattern="^(en|bn)$")


class FeedbackIn(BaseModel):
    session_id: str
    message_id: str
    rating: Annotated[int, Field(ge=-1, le=1)]
    comment: str | None = None


@router.post("/stream")
async def chat_stream(body: ChatIn, service: CatalogServiceDep) -> StreamingResponse:
    return StreamingResponse(stream_answer(service, body.question), media_type="text/event-stream")


@router.post("/feedback", status_code=204)
async def chat_feedback(body: FeedbackIn, session: SessionDep) -> None:
    import uuid

    session.add(
        ChatFeedback(
            session_id=uuid.UUID(body.session_id),
            message_id=body.message_id,
            rating=body.rating,
            comment=body.comment,
        )
    )
    await session.commit()
