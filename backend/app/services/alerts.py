import uuid

from pydantic import BaseModel, Field

from app.config import Settings
from app.db.repositories.subscribers import SubscriberRepository
from app.errors import AppError
from app.notify import mailer, tokens

GENERIC_OK = "If this address can receive mail, you will get a confirmation message shortly."


class SubscribeIn(BaseModel):
    email: str = Field(min_length=5, max_length=120)
    locale: str = Field(default="en", pattern="^(en|bn)$")
    frequency: str = Field(default="weekly", pattern="^(immediate|weekly)$")
    min_severity: str = Field(default="major", pattern="^(boxed|major|moderate|minor)$")
    drug_ids: list[uuid.UUID] = Field(default_factory=list, max_length=25)
    consent: bool
    website: str = ""


class SubscribeOut(BaseModel):
    message: str = GENERIC_OK


class AlertsService:
    def __init__(self, repo: SubscriberRepository, settings: Settings) -> None:
        self._repo = repo
        self._settings = settings

    async def subscribe(self, body: SubscribeIn) -> SubscribeOut:
        if body.website:
            return SubscribeOut()
        if not body.consent:
            raise AppError(422, "Consent is required.")
        if not body.drug_ids:
            raise AppError(422, "Choose at least one medicine to watch.")
        secret = self._settings.email_token_secret
        if secret is None:
            raise AppError(503, "Email alerts are not configured yet.")
        subscriber = await self._repo.create_pending(
            email=body.email,
            locale=body.locale,
            frequency=body.frequency,
            min_severity=body.min_severity,
            consent_version=self._settings.consent_version,
            drug_ids=body.drug_ids,
        )
        token = tokens.mint(secret.get_secret_value(), "confirm", subscriber.id)
        link = f"{self._settings.frontend_base_url}/alerts/confirm?token={token}"
        await mailer.send(
            self._settings,
            to=body.email,
            subject="Confirm your Label Lag Radar alerts",
            text=f"Open this link to confirm: {link}\n\nNot medical advice.",
        )
        return SubscribeOut()
