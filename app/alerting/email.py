"""Email delivery -- a second alert channel alongside Web Push (app/alerting/push.py),
opt-in per SlotWatch/Subscription rather than a global setting (docs/DECISIONS.md).

Plain stdlib `smtplib`, no new dependency. Written for the Gmail "app password" convention
(STARTTLS on port 587, log in with a real address + a 16-character app password from
Google account settings) since that's what this project is configured against, but nothing
here is Gmail-specific -- any standard SMTP+STARTTLS server works via the same settings.

Degrades the same way push.py degrades on blank VAPID keys: a missing smtp_password logs a
warning and returns False rather than raising -- one delivery channel being unconfigured
must never break the other, or break the caller (hard rule 7).
"""
import logging
import smtplib
from email.mime.text import MIMEText

from app.logging_utils import log_event
from app.settings import get_settings

logger = logging.getLogger("alerting.email")


def send_email(to_email: str, subject: str, body: str) -> bool:
    settings = get_settings()
    if not settings.smtp_user or not settings.smtp_password:
        log_event(logger, logging.WARNING, "email not sent -- SMTP not configured", to=to_email)
        return False

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from or settings.smtp_user
    msg["To"] = to_email

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
        return True
    except Exception as exc:  # noqa: BLE001 -- a delivery failure must not raise into the caller
        log_event(logger, logging.ERROR, "email send failed", to=to_email, error=str(exc))
        return False
