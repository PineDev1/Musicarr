from __future__ import annotations

from unittest.mock import patch

from app.models import AppSettings
from app.services.notifications import send_notification


def _settings(db, **kwargs) -> AppSettings:
    row = AppSettings(id=1, **kwargs)
    db.add(row)
    db.commit()
    return row


def test_send_notification_pushes_even_without_webhook_configured(db):
    _settings(db, notify_webhook_url="")
    with patch("app.services.push.send_push") as mock_push:
        send_notification(db, "Title", "Body", kind="complete")
    mock_push.assert_called_once()


def test_send_notification_skips_push_when_kind_disabled(db):
    _settings(db, notify_webhook_url="", notify_on_complete=False)
    with patch("app.services.push.send_push") as mock_push:
        send_notification(db, "Title", "Body", kind="complete")
    mock_push.assert_not_called()
