"""410 handling -- prompts/phase-4-alerting.md acceptance check 4. No live push service in
tests (no live network, same policy as the ingestion clients) -- pywebpush.webpush is
monkeypatched, same methodology as respx for httpx in Phase 1.
"""
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from pywebpush import WebPushException

from app.alerting.push import PushResult, send_push
from app.alerting.runner import deliver_to_user
from app.models import PushSubscription


def _push_sub(**kwargs):
    defaults = dict(
        id=1, user_id="u1", endpoint="https://push.example/abc", p256dh="key", auth="auth",
        active=True, created_at=datetime.now(UTC),
    )
    defaults.update(kwargs)
    return PushSubscription(**defaults)


def test_410_response_classified_as_expired():
    resp = MagicMock()
    resp.status_code = 410
    exc = WebPushException("gone", response=resp)
    with patch("app.alerting.push.webpush", side_effect=exc):
        with patch("app.alerting.push.get_settings") as gs:
            gs.return_value.vapid_private_key = "priv"
            gs.return_value.vapid_public_key = "pub"
            gs.return_value.vapid_claims_email = "a@b.com"
            result = send_push(_push_sub(), {"title": "test"})
    assert result == PushResult.EXPIRED


def test_404_response_also_classified_as_expired():
    resp = MagicMock()
    resp.status_code = 404
    exc = WebPushException("not found", response=resp)
    with patch("app.alerting.push.webpush", side_effect=exc):
        with patch("app.alerting.push.get_settings") as gs:
            gs.return_value.vapid_private_key = "priv"
            gs.return_value.vapid_public_key = "pub"
            gs.return_value.vapid_claims_email = "a@b.com"
            result = send_push(_push_sub(), {"title": "test"})
    assert result == PushResult.EXPIRED


def test_other_failure_classified_as_failed_not_expired():
    resp = MagicMock()
    resp.status_code = 500
    exc = WebPushException("server error", response=resp)
    with patch("app.alerting.push.webpush", side_effect=exc):
        with patch("app.alerting.push.get_settings") as gs:
            gs.return_value.vapid_private_key = "priv"
            gs.return_value.vapid_public_key = "pub"
            gs.return_value.vapid_claims_email = "a@b.com"
            result = send_push(_push_sub(), {"title": "test"})
    assert result == PushResult.FAILED


@pytest.mark.asyncio
async def test_expired_push_subscription_is_deactivated_not_retried(db_session):
    push_sub = _push_sub()
    db_session.add(push_sub)
    await db_session.commit()

    resp = MagicMock()
    resp.status_code = 410
    exc = WebPushException("gone", response=resp)

    with patch("app.alerting.push.webpush", side_effect=exc):
        with patch("app.alerting.push.get_settings") as gs:
            gs.return_value.vapid_private_key = "priv"
            gs.return_value.vapid_public_key = "pub"
            gs.return_value.vapid_claims_email = "a@b.com"
            await deliver_to_user(db_session, "u1", {"title": "test"})

    await db_session.refresh(push_sub)
    assert push_sub.active is False
