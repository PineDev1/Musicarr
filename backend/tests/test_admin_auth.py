from __future__ import annotations

import pytest

from app.models import AppSettings
from app.services import admin_auth, app_auth


def _settings(db) -> AppSettings:
    row = AppSettings(
        id=1,
        auth_enabled=True,
        auth_username="admin",
        auth_password_hash=app_auth.hash_password("legacy-pw"),
    )
    db.add(row)
    db.commit()
    return row


def test_create_and_authenticate_admin_user(db):
    _settings(db)
    user = admin_auth.create_user(db, username="riley", password="hunter22", display_name="Riley")

    assert admin_auth.authenticate(db, "riley", "hunter22").id == user.id
    assert admin_auth.authenticate(db, "riley", "wrong-pw") is None


def test_duplicate_username_rejected(db):
    _settings(db)
    admin_auth.create_user(db, username="riley", password="hunter22")
    with pytest.raises(ValueError):
        admin_auth.create_user(db, username="riley", password="other-pw")


def test_session_token_round_trips_for_legacy_and_admin_user(db):
    _settings(db)
    user = admin_auth.create_user(db, username="riley", password="hunter22")

    legacy_token = app_auth.create_session_token(db, "admin")
    assert app_auth.parse_session_token(db, legacy_token) == "admin"

    user_token = app_auth.create_session_token(db, user.username, user_id=user.id)
    assert app_auth.parse_session_token(db, user_token) == "riley"


def test_deactivated_admin_user_session_rejected(db):
    _settings(db)
    user = admin_auth.create_user(db, username="riley", password="hunter22")
    token = app_auth.create_session_token(db, user.username, user_id=user.id)

    admin_auth.update_user(db, user.id, is_active=False)

    assert app_auth.parse_session_token(db, token) is None


def test_deleted_admin_user_session_rejected(db):
    _settings(db)
    user = admin_auth.create_user(db, username="riley", password="hunter22")
    token = app_auth.create_session_token(db, user.username, user_id=user.id)

    admin_auth.delete_user(db, user.id)

    assert app_auth.parse_session_token(db, token) is None
