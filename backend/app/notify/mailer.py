"""SMTP send with dry-run to var/outbox/."""

from email.message import EmailMessage
from pathlib import Path

from app.config import Settings

OUTBOX = Path(__file__).resolve().parents[3] / "var" / "outbox"


async def send(
    settings: Settings, *, to: str, subject: str, text: str, html: str | None = None
) -> str:
    if settings.email_dry_run or not settings.smtp_host:
        OUTBOX.mkdir(parents=True, exist_ok=True)
        safe = subject.replace(" ", "_")[:40]
        path = OUTBOX / f"{safe}.eml"
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = (
            f"{settings.email_from_name} <{settings.email_from_address or 'noreply@localhost'}>"
        )
        msg["To"] = to
        msg.set_content(text)
        if html:
            msg.add_alternative(html, subtype="html")
        path.write_bytes(msg.as_bytes())
        return f"dry-run:{path.name}"
    raise NotImplementedError("Live SMTP is configured in settings but send is not wired yet.")
