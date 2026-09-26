from __future__ import annotations

from unittest.mock import patch

from app.models import AppSettings, PushSubscription
from app.services import push


def _settings(db) -> AppSettings:
    row = AppSettings(id=1)
    db.add(row)
    db.commit()
    return row


def test_ensure_vapid_keys_generates_and_persists_once(db):
    _settings(db)
    pub1, priv1 = push.ensure_vapid_keys(db)
    assert pub1 and priv1
    pub2, priv2 = push.ensure_vapid_keys(db)
    assert (pub1, priv1) == (pub2, priv2)


def test_add_and_remove_subscription(db):
    _settings(db)
    row = push.add_subscription(db, endpoint="https://push.example/1", p256dh="p", auth="a")
    assert row.id is not None

    # Re-subscribing the same endpoint updates rather than duplicates.
    push.add_subscription(db, endpoint="https://push.example/1", p256dh="p2", auth="a2")
    rows = db.query(PushSubscription).all()
    assert len(rows) == 1
    assert rows[0].p256dh == "p2"

    push.remove_subscription(db, "https://push.example/1")
    assert db.query(PushSubscription).count() == 0


def test_send_push_noop_with_no_subscriptions(db):
    _settings(db)
    assert push.send_push(db, "Title", "Body") == 0


def test_send_push_calls_webpush_for_each_subscription(db):
    _settings(db)
    push.add_subscription(db, endpoint="https://push.example/1", p256dh="p1", auth="a1")
    push.add_subscription(db, endpoint="https://push.example/2", p256dh="p2", auth="a2")

    calls = []
    with patch("app.services.push.webpush", lambda **kw: calls.append(kw)):
        sent = push.send_push(db, "Title", "Body")

    assert sent == 2
    assert len(calls) == 2
    endpoints = {c["subscription_info"]["endpoint"] for c in calls}
    assert endpoints == {"https://push.example/1", "https://push.example/2"}


def test_send_push_prunes_gone_subscription(db):
    from pywebpush import WebPushException

    _settings(db)
    push.add_subscription(db, endpoint="https://push.example/dead", p256dh="p", auth="a")

    class FakeResponse:
        status_code = 410

    def _raise(**kw):
        raise WebPushException("gone", response=FakeResponse())

    with patch("app.services.push.webpush", _raise):
        sent = push.send_push(db, "Title", "Body")

    assert sent == 0
    assert db.query(PushSubscription).count() == 0
