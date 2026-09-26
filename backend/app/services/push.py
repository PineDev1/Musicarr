from __future__ import annotations

import base64
import logging

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid
from pywebpush import WebPushException, webpush
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PushSubscription
from app.services.settings_service import ensure_settings

logger = logging.getLogger("musicarr.push")

VAPID_CLAIMS_SUB = "mailto:admin@musicarr.local"


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def ensure_vapid_keys(db: Session) -> tuple[str, str]:
    """Return (public_key_b64url, private_key_pem), generating and persisting
    a keypair the first time this instance ever needs one."""
    settings = ensure_settings(db)
    pub = getattr(settings, "vapid_public_key", "") or ""
    priv = getattr(settings, "vapid_private_key", "") or ""
    if pub and priv:
        return pub, priv

    vapid = Vapid()
    vapid.generate_keys()
    raw_pub = vapid.public_key.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    pub = _b64url(raw_pub)
    priv = vapid.private_pem().decode("ascii")
    settings.vapid_public_key = pub
    settings.vapid_private_key = priv
    db.commit()
    return pub, priv


def add_subscription(db: Session, *, endpoint: str, p256dh: str, auth: str) -> PushSubscription:
    existing = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == endpoint))
    if existing:
        existing.p256dh = p256dh
        existing.auth = auth
        db.commit()
        return existing
    row = PushSubscription(endpoint=endpoint, p256dh=p256dh, auth=auth)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def remove_subscription(db: Session, endpoint: str) -> None:
    row = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == endpoint))
    if row:
        db.delete(row)
        db.commit()


def send_push(db: Session, title: str, message: str, *, url: str = "/") -> int:
    """Push to every stored subscription; prunes any endpoint the push
    service reports as gone (410/404). Returns the number of successful
    sends. A no-op (returns 0) if no subscriptions exist yet — most
    notifications fire with none registered, so this must stay cheap."""
    rows = list(db.scalars(select(PushSubscription)).all())
    if not rows:
        return 0
    pub, priv = ensure_vapid_keys(db)
    payload = f'{{"title":{_json_str(title)},"body":{_json_str(message)},"url":{_json_str(url)}}}'
    sent = 0
    for row in rows:
        subscription_info = {
            "endpoint": row.endpoint,
            "keys": {"p256dh": row.p256dh, "auth": row.auth},
        }
        try:
            webpush(
                subscription_info=subscription_info,
                data=payload,
                vapid_private_key=priv,
                vapid_claims={"sub": VAPID_CLAIMS_SUB},
                timeout=8,
            )
            sent += 1
        except WebPushException as exc:
            status = getattr(exc.response, "status_code", None)
            if status in (404, 410):
                db.delete(row)
                db.commit()
            else:
                logger.warning("Web push failed for a subscription: %s", exc)
        except Exception:  # noqa: BLE001
            logger.warning("Web push failed for a subscription", exc_info=True)
    return sent


def _json_str(value: str) -> str:
    import json

    return json.dumps(value or "")
