"""TypeSafe Jev client. Disabled unless JEV_ENABLED=true and TYPESAFE_API_KEY is set."""

from app.config import Settings
from app.errors import AppError


class JevClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def enabled(self) -> bool:
        return self._settings.jev_enabled and self._settings.typesafe_api_key is not None

    async def systemone(
        self, state: object, questions: list[dict[str, object]]
    ) -> dict[str, object]:
        if not self.enabled:
            raise AppError(503, "Jev is disabled.")
        raise NotImplementedError("Wire Jev against docs/JEV_API.md when enabled.")
