from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from sqlalchemy.orm import Session

from app.services.settings_service import ensure_settings

logger = logging.getLogger("musicarr.notify")


def _post_json(url: str, payload: dict, *, headers: dict[str, str] | None = None) -> None:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Musicarr/1.6",
            **(headers or {}),
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=8) as resp:  # noqa: S310
        resp.read()


def _post_form(url: str, fields: dict[str, str]) -> None:
    data = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Musicarr/1.6",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=8) as resp:  # noqa: S310
        resp.read()


def send_notification(
    db: Session,
    title: str,
    message: str,
    *,
    kind: str = "info",
    webhook_url: str | None = None,
    channel: str | None = None,
    token: str | None = None,
) -> None:
    settings = ensure_settings(db)
    # Overrides let a caller (e.g. "send test notification") try unsaved form
    # values instead of only what's already persisted.
    url = (webhook_url if webhook_url is not None else getattr(settings, "notify_webhook_url", None) or "").strip()
    if not url:
        return
    if kind == "complete" and not getattr(settings, "notify_on_complete", True):
        return
    if kind in {"failure", "auth"} and not getattr(settings, "notify_on_failure", True):
        return
    if kind == "library" and not getattr(settings, "notify_on_library_events", False):
        return
    if kind == "maintenance" and not getattr(settings, "notify_on_maintenance", True):
        return
    if kind == "health" and not getattr(settings, "notify_on_health_alerts", True):
        return
    channel = (channel if channel is not None else getattr(settings, "notify_channel", None) or "custom").strip().lower() or "custom"
    token = (token if token is not None else getattr(settings, "notify_token", None) or "").strip()
    content = f"{title}\n{message}"
    try:
        if channel == "discord":
            _post_json(
                url,
                {
                    "content": content[:1900],
                    "embeds": [
                        {
                            "title": title[:250],
                            "description": message[:1900],
                            "color": 0x3DBA7A if kind == "complete" else 0xC44 if kind in {"failure", "auth"} else 0x888888,
                        }
                    ],
                },
            )
        elif channel == "slack":
            _post_json(
                url,
                {
                    "text": content[:3000],
                    "blocks": [
                        {
                            "type": "section",
                            "text": {"type": "mrkdwn", "text": f"*{title}*\n{message}"[:2900]},
                        }
                    ],
                },
            )
        elif channel == "ntfy":
            # URL is the topic endpoint, e.g. https://ntfy.sh/mytopic
            # HTTP headers must be latin-1; percent-encode the title so non-ASCII
            # artist/album names (CJK, Cyrillic, emoji, accents) can't crash the send.
            headers = {"Title": urllib.parse.quote(title[:250]), "Tags": "music"}
            if token:
                headers["Authorization"] = f"Bearer {token}"
            req = urllib.request.Request(
                url,
                data=message.encode("utf-8"),
                headers={"User-Agent": "Musicarr/1.6", **headers},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=8) as resp:  # noqa: S310
                resp.read()
        elif channel == "pushover":
            if not token:
                logger.warning("Pushover notify skipped: notify_token (user key) missing")
                return
            # URL field holds the app token when using Pushover preset
            _post_form(
                "https://api.pushover.net/1/messages.json",
                {
                    "token": url,
                    "user": token,
                    "title": title[:250],
                    "message": message[:1024],
                },
            )
        else:
            # Custom / generic webhook
            _post_json(
                url,
                {
                    "content": content[:1900],
                    "text": content[:1900],
                    "message": content[:1900],
                    "title": title,
                    "kind": kind,
                },
            )
    except (urllib.error.URLError, TimeoutError, OSError, UnicodeError, ValueError) as exc:
        logger.warning("Webhook notify failed: %s", exc)


def send_test_notification(
    db: Session,
    *,
    webhook_url: str | None = None,
    channel: str | None = None,
    token: str | None = None,
) -> None:
    send_notification(
        db,
        "Musicarr test",
        "Notifications are working.",
        kind="info",
        webhook_url=webhook_url,
        channel=channel,
        token=token,
    )
