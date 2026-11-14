from typing import Annotated

from fastapi import APIRouter, Query

from app.db.repositories.subscribers import SubscriberRepository
from app.deps import AlertsServiceDep, SessionDep, SettingsDep
from app.errors import AppError
from app.notify import tokens
from app.services.alerts import SubscribeIn, SubscribeOut

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.post("/subscribe", response_model=SubscribeOut, status_code=202)
async def subscribe(
    body: SubscribeIn, service: AlertsServiceDep, session: SessionDep
) -> SubscribeOut:
    out = await service.subscribe(body)
    await session.commit()
    return out


@router.get("/confirm")
async def confirm(token: str, session: SessionDep, settings: SettingsDep) -> dict[str, str]:
    secret = settings.email_token_secret
    if secret is None:
        raise AppError(503, "Email alerts are not configured.")
    sub_id = tokens.verify(secret.get_secret_value(), token, "confirm")
    row = await SubscriberRepository(session).confirm(sub_id)
    if row is None:
        raise AppError(404, "Subscription not found.")
    await session.commit()
    return {"status": "active", "message": "Your alerts are confirmed. Not medical advice."}


@router.post("/unsubscribe")
async def unsubscribe(
    token: Annotated[str, Query()],
    session: SessionDep,
    settings: SettingsDep,
) -> dict[str, str]:
    secret = settings.email_token_secret
    if secret is None:
        raise AppError(503, "Email alerts are not configured.")
    sub_id = tokens.verify(secret.get_secret_value(), token, "unsub")
    await SubscriberRepository(session).unsubscribe(sub_id)
    await session.commit()
    return {"status": "unsubscribed"}
