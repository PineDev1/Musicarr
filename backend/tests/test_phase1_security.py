from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.api.player import _require_admin
from app.models import AppSettings, Artist
from app.services import app_auth
from app.services.artists import _legacy_id, find_artist_by_normalized_name
from app.services.settings_service import ensure_settings


def _settings(db, **kwargs) -> AppSettings:
    row = ensure_settings(db)
    for key, value in kwargs.items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return row


def test_require_admin_rejects_when_auth_disabled(db):
    _settings(db, auth_enabled=False)
    req = MagicMock()
    req.cookies = {}
    with pytest.raises(HTTPException) as exc:
        _require_admin(req, db)
    assert exc.value.status_code == 401
    assert "Security" in str(exc.value.detail)


def test_require_admin_rejects_without_cookie(db):
    _settings(db, auth_enabled=True, auth_username="admin", auth_password_hash=app_auth.hash_password("x"))
    req = MagicMock()
    req.cookies = {}
    with pytest.raises(HTTPException) as exc:
        _require_admin(req, db)
    assert exc.value.status_code == 401


def test_require_admin_accepts_valid_session(db):
    _settings(db, auth_enabled=True, auth_username="admin", auth_password_hash=app_auth.hash_password("x"))
    token = app_auth.create_session_token(db, "admin")
    req = MagicMock()
    req.cookies = {app_auth.COOKIE_NAME: token}
    _require_admin(req, db)  # does not raise


def test_legacy_id_is_deterministic():
    a = _legacy_id("qobuz", "12345")
    b = _legacy_id("qobuz", "12345")
    assert a == b
    assert a == _legacy_id("qobuz", "12345")
    assert _legacy_id("deezer", "99") == 99
    assert _legacy_id("tidal", "99") != 99


def test_find_artist_by_normalized_name(db):
    db.add(
        Artist(
            provider="qobuz",
            provider_id="1",
            deezer_id=1,
            name="Luke  Combs",
            monitored=True,
        )
    )
    db.commit()
    hit = find_artist_by_normalized_name(db, "luke combs", "qobuz")
    assert hit is not None
    assert hit.provider_id == "1"
    assert find_artist_by_normalized_name(db, "Nope", "qobuz") is None
