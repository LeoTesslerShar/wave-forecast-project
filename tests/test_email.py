"""Email delivery -- app/alerting/email.py. No live network (PROMPT.md section 3):
smtplib.SMTP is monkeypatched, same methodology as respx for httpx elsewhere."""
from unittest.mock import MagicMock, patch

from app.alerting.email import send_email


def test_missing_smtp_credentials_degrades_to_false_not_a_crash():
    with patch("app.alerting.email.get_settings") as gs:
        gs.return_value.smtp_user = ""
        gs.return_value.smtp_password = ""
        result = send_email("surfer@example.com", "subject", "body")
    assert result is False


def test_successful_send_returns_true_and_logs_in():
    smtp_instance = MagicMock()
    smtp_instance.__enter__.return_value = smtp_instance
    with patch("app.alerting.email.smtplib.SMTP", return_value=smtp_instance) as smtp_cls:
        with patch("app.alerting.email.get_settings") as gs:
            gs.return_value.smtp_user = "me@gmail.com"
            gs.return_value.smtp_password = "app-password"
            gs.return_value.smtp_host = "smtp.gmail.com"
            gs.return_value.smtp_port = 587
            gs.return_value.smtp_from = ""
            result = send_email("surfer@example.com", "subject", "body")

    assert result is True
    smtp_cls.assert_called_once_with("smtp.gmail.com", 587, timeout=10)
    smtp_instance.starttls.assert_called_once()
    smtp_instance.login.assert_called_once_with("me@gmail.com", "app-password")
    smtp_instance.send_message.assert_called_once()


def test_smtp_failure_degrades_to_false_not_a_crash():
    with patch("app.alerting.email.smtplib.SMTP", side_effect=OSError("connection refused")):
        with patch("app.alerting.email.get_settings") as gs:
            gs.return_value.smtp_user = "me@gmail.com"
            gs.return_value.smtp_password = "app-password"
            gs.return_value.smtp_host = "smtp.gmail.com"
            gs.return_value.smtp_port = 587
            result = send_email("surfer@example.com", "subject", "body")
    assert result is False
