from __future__ import annotations

import pytest
from fastapi import HTTPException, Response

from app.api import auth
from app.models.schemas import AppLoginRequest
from app.services import login_throttle
from app.services.settings_service import ensure_settings


def _enable_auth(db):
    row = ensure_settings(db)
    row.auth_enabled = True
    db.commit()


def test_repeated_wrong_passwords_get_throttled_then_429(db):
    _enable_auth(db)
    for _ in range(login_throttle.MAX_PER_USERNAME):
        with pytest.raises(HTTPException) as e:
            auth.app_login(AppLoginRequest(username="victim", password="guess"), Response(), db)
        assert e.value.status_code == 401
    with pytest.raises(HTTPException) as e:
        auth.app_login(AppLoginRequest(username="victim", password="guess"), Response(), db)
    assert e.value.status_code == 429 and int(e.value.headers["Retry-After"]) > 0


def test_non_ascii_username_is_a_401_not_a_500(db):
    _enable_auth(db)
    with pytest.raises(HTTPException) as e:
        auth.app_login(AppLoginRequest(username="rïley", password="x"), Response(), db)
    assert e.value.status_code == 401


def test_window_expires_old_failures(db, monkeypatch):
    for _ in range(login_throttle.MAX_PER_USERNAME):
        login_throttle.record_failure("admin", "1.2.3.4", "bob")
    assert login_throttle.retry_after("admin", "1.2.3.4", "bob") > 0
    real = login_throttle.time.time
    monkeypatch.setattr(login_throttle.time, "time", lambda: real() + login_throttle.WINDOW_SECONDS + 5)
    assert login_throttle.retry_after("admin", "1.2.3.4", "bob") == 0


def test_success_clears_username_bucket(db):
    for _ in range(3):
        login_throttle.record_failure("admin", "9.9.9.9", "carol")
    login_throttle.record_success("admin", "9.9.9.9", "carol")
    for _ in range(login_throttle.MAX_PER_USERNAME - 1):
        login_throttle.record_failure("admin", "9.9.9.9", "carol")
    assert login_throttle.retry_after("admin", "9.9.9.9", "carol") == 0
