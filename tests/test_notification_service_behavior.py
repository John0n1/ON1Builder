import asyncio
from types import SimpleNamespace

import pytest

from on1builder.config.settings import NotificationSettings
from on1builder.utils import notification_service as notification_module
from on1builder.utils.notification_service import NotificationService


class _DummyResponse:
    def __init__(self, status: int = 200, ok: bool = True):
        self.status = status
        self.ok = ok

    async def text(self) -> str:
        return ""

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _DummySession:
    def __init__(self):
        self.calls = []
        self.closed = False

    def post(self, url, json):
        self.calls.append((url, json))
        return _DummyResponse()


@pytest.mark.asyncio
async def test_notification_service_sends_configured_channels(monkeypatch):
    NotificationService.reset_instance()

    stub_settings = SimpleNamespace(
        notifications=NotificationSettings(
            channels=["slack", "discord", "telegram", "email"],
            min_level="INFO",
            slack_webhook_url="https://example.com/slack",
            discord_webhook_url="https://example.com/discord",
            telegram_bot_token="bot-token",
            telegram_chat_id="12345",
            smtp_server="smtp.example.com",
            smtp_port=25,
            smtp_username="alerts@example.com",
            smtp_password="secret",
            alert_email="ops@example.com",
        )
    )

    dummy_session = _DummySession()
    sent_emails = []

    monkeypatch.setattr(notification_module, "get_settings", lambda: stub_settings)

    async def fake_get_session(self):
        return dummy_session

    monkeypatch.setattr(NotificationService, "_get_session", fake_get_session, raising=False)

    async def fake_to_thread(func, *args, **kwargs):
        result = func(*args, **kwargs)
        sent_emails.append("thread-dispatched")
        return result

    def fake_send_smtp(self, msg):
        sent_emails.append(msg["Subject"])

    monkeypatch.setattr(notification_module.asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(NotificationService, "_send_smtp_email", fake_send_smtp, raising=False)

    notification_service = NotificationService()

    details = {"order_id": "123", "reason": "imbalance"}
    await notification_service.send_alert(
        title="Imbalance detected",
        message="Rebalance required",
        level="ERROR",
        details=details,
    )

    assert len(dummy_session.calls) == 3  # slack, discord, telegram
    assert any("slack" in call[0] for call in dummy_session.calls)
    assert sent_emails, "Email notifications should be routed through SMTP helper"

    # Backward compatibility helpers resolve configuration lazily
    assert notification_service.config is not None
    assert notification_service.settings is notification_service.config
    assert notification_service.level_to_int("warning") == 2

    await notification_service.close()
    NotificationService.reset_instance()
