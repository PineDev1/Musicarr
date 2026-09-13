from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from sqlalchemy.orm import Session

from app.services.settings_service import ensure_settings

logger = logging.getLogger("musicarr.notify")


def _post_json(url: str, payload: dict) -> None:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "Musicarr/1.1"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=8) as resp:  # noqa: S310
        resp.read()


def send_notification(db: Session, title: str, message: str, *, kind: str = "info") -> None:
    settings = ensure_settings(db)
    url = (getattr(settings, "notify_webhook_url", None) or "").strip()
    if not url:
        return
    if kind == "complete" and not getattr(settings, "notify_on_complete", True):
        return
    if kind in {"failure", "auth"} and not getattr(settings, "notify_on_failure", True):
        return
    # Discord-compatible + generic webhook body
    content = f"**{title}**\n{message}"
    payload = {
        "content": content[:1900],
        "text": content[:1900],
        "message": content[:1900],
        "title": title,
        "kind": kind,
    }
    try:
        _post_json(url, payload)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.warning("Webhook notify failed: %s", exc)
