from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.harness.pipeline import _send_slack_notification


def test_send_slack_notification_skipped_without_webhook(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.harness.pipeline.get_settings", lambda: SimpleNamespace(slack_webhook_url="")
    )
    fake_post = MagicMock()
    monkeypatch.setattr("app.harness.pipeline.httpx.post", fake_post)

    _send_slack_notification("test")

    fake_post.assert_not_called()


def test_send_slack_notification_posts_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    webhook_url = "https://hooks.slack.example/services/x"
    monkeypatch.setattr(
        "app.harness.pipeline.get_settings",
        lambda: SimpleNamespace(slack_webhook_url=webhook_url),
    )
    fake_post = MagicMock()
    monkeypatch.setattr("app.harness.pipeline.httpx.post", fake_post)

    _send_slack_notification("本日の候補10件(要確認0件)")

    fake_post.assert_called_once_with(
        webhook_url, json={"text": "本日の候補10件(要確認0件)"}, timeout=5.0
    )


def test_send_slack_notification_swallow_http_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    monkeypatch.setattr(
        "app.harness.pipeline.get_settings",
        lambda: SimpleNamespace(slack_webhook_url="https://hooks.slack.example/services/x"),
    )

    def _raise(*args: Any, **kwargs: Any) -> None:
        raise httpx.ConnectError("boom")

    monkeypatch.setattr("app.harness.pipeline.httpx.post", _raise)

    _send_slack_notification("test")  # should not raise
