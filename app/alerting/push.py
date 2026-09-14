"""Web Push delivery -- prompts/phase-4-alerting.md section 5. VAPID keys from env, never
committed (hard rule 4)."""
import json
import logging

from pywebpush import WebPushException, webpush

from app.logging_utils import log_event
from app.models import PushSubscription
from app.settings import get_settings

logger = logging.getLogger("alerting.push")


class PushResult:
    SENT = "sent"
    EXPIRED = "expired"  # 404/410 -- deactivate, do not retry
    FAILED = "failed"    # other failure -- caller may retry with backoff


def send_push(push_sub: PushSubscription, payload: dict) -> str:
    settings = get_settings()
    if not settings.vapid_private_key or not settings.vapid_public_key:
        log_event(logger, logging.WARNING, "VAPID keys not configured, skipping push", push_id=push_sub.id)
        return PushResult.FAILED

    try:
        webpush(
            subscription_info={
                "endpoint": push_sub.endpoint,
                "keys": {"p256dh": push_sub.p256dh, "auth": push_sub.auth},
            },
            data=json.dumps(payload, default=str),
            vapid_private_key=settings.vapid_private_key,
            vapid_claims={"sub": f"mailto:{settings.vapid_claims_email}"},
        )
        return PushResult.SENT
    except WebPushException as exc:
        status = exc.response.status_code if exc.response is not None else None
        if status in (404, 410):
            log_event(
                logger, logging.INFO, "push subscription expired, deactivating",
                push_id=push_sub.id, status=status,
            )
            return PushResult.EXPIRED
        log_event(
            logger, logging.WARNING, "push send failed", push_id=push_sub.id, status=status, error=str(exc)
        )
        return PushResult.FAILED
