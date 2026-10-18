from typing import Any

import pytest

from config import get_settings
from services import email


async def test_dev_mode_does_not_send(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "smtp_host", "")

    def boom(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("SMTP must not be used in dev mode")

    import aiosmtplib

    monkeypatch.setattr(aiosmtplib, "send", boom)
    await email.send_verification_email("a@example.com", "tok")


async def test_smtp_mode_builds_message(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(settings, "smtp_user", "bot@example.com")
    monkeypatch.setattr(settings, "public_app_url", "https://app.example.com")
    sent: dict[str, Any] = {}

    async def fake_send(msg: Any, **kwargs: Any) -> None:
        sent["msg"] = msg
        sent["kwargs"] = kwargs

    import aiosmtplib

    monkeypatch.setattr(aiosmtplib, "send", fake_send)
    await email.send_verification_email("a+b@example.com", "tok123")

    msg = sent["msg"]
    assert msg["To"] == "a+b@example.com"
    assert msg["From"] == "bot@example.com"
    body = msg.get_body(preferencelist=("plain",)).get_content()
    assert "https://app.example.com/verify?token=tok123&email=a%2Bb%40example.com" in body
    assert sent["kwargs"]["hostname"] == "smtp.example.com"
    assert sent["kwargs"]["username"] == "bot@example.com"


async def test_smtp_failure_is_swallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "smtp_host", "smtp.example.com")

    async def failing_send(*args: Any, **kwargs: Any) -> None:
        raise OSError("connection refused")

    import aiosmtplib

    monkeypatch.setattr(aiosmtplib, "send", failing_send)
    await email.send_verification_email("a@example.com", "tok")
