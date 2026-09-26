from __future__ import annotations

import pyotp
import pytest
from fastapi import HTTPException
from fastapi.responses import Response

from app.api.auth import app_login
from app.models import AppSettings
from app.models.schemas import AppLoginRequest
from app.services import admin_auth
from app.services.app_auth import hash_password


def _settings(db) -> AppSettings:
    row = AppSettings(
        id=1,
        auth_enabled=True,
        auth_username="admin",
        auth_password_hash=hash_password("legacy-pw"),
    )
    db.add(row)
    db.commit()
    return row


def test_login_without_totp_enabled_succeeds_normally(db):
    _settings(db)
    admin_auth.create_user(db, username="riley", password="hunter22")

    status = app_login(AppLoginRequest(username="riley", password="hunter22"), Response(), db)
    assert status.authenticated is True


def test_login_with_totp_enabled_requires_code(db):
    _settings(db)
    user = admin_auth.create_user(db, username="riley", password="hunter22")
    secret, _ = admin_auth.start_totp_setup(db, user.id)
    admin_auth.confirm_totp(db, user.id, pyotp.TOTP(secret).now())

    with pytest.raises(HTTPException) as exc:
        app_login(AppLoginRequest(username="riley", password="hunter22"), Response(), db)
    assert exc.value.status_code == 401
    assert exc.value.detail == "totp_required"

    with pytest.raises(HTTPException) as exc:
        app_login(
            AppLoginRequest(username="riley", password="hunter22", totp_code="000000"),
            Response(),
            db,
        )
    assert exc.value.detail == "totp_required"

    status = app_login(
        AppLoginRequest(username="riley", password="hunter22", totp_code=pyotp.TOTP(secret).now()),
        Response(),
        db,
    )
    assert status.authenticated is True
