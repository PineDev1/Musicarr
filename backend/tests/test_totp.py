from __future__ import annotations

import pyotp
import pytest

from app.services import admin_auth, totp


def _user(db):
    return admin_auth.create_user(db, username="riley", password="hunter22")


def test_totp_setup_and_confirm_flow(db):
    user = _user(db)
    secret, url = admin_auth.start_totp_setup(db, user.id)
    assert secret
    assert "otpauth://totp/" in url
    db.refresh(user)
    assert user.totp_enabled is False

    code = pyotp.TOTP(secret).now()
    admin_auth.confirm_totp(db, user.id, code)
    db.refresh(user)
    assert user.totp_enabled is True


def test_confirm_totp_rejects_wrong_code(db):
    user = _user(db)
    admin_auth.start_totp_setup(db, user.id)
    with pytest.raises(ValueError):
        admin_auth.confirm_totp(db, user.id, "000000")
    db.refresh(user)
    assert user.totp_enabled is False


def test_verify_totp_for_login(db):
    user = _user(db)
    secret, _ = admin_auth.start_totp_setup(db, user.id)
    admin_auth.confirm_totp(db, user.id, pyotp.TOTP(secret).now())
    db.refresh(user)

    assert admin_auth.verify_totp_for_login(user, None) is False
    assert admin_auth.verify_totp_for_login(user, "000000") is False
    assert admin_auth.verify_totp_for_login(user, pyotp.TOTP(secret).now()) is True


def test_verify_totp_for_login_passes_through_when_disabled(db):
    user = _user(db)
    assert admin_auth.verify_totp_for_login(user, None) is True


def test_disable_totp_requires_valid_code(db):
    user = _user(db)
    secret, _ = admin_auth.start_totp_setup(db, user.id)
    admin_auth.confirm_totp(db, user.id, pyotp.TOTP(secret).now())
    db.refresh(user)

    with pytest.raises(ValueError):
        admin_auth.disable_totp(db, user.id, "000000")

    admin_auth.disable_totp(db, user.id, pyotp.TOTP(secret).now())
    db.refresh(user)
    assert user.totp_enabled is False
    assert user.totp_secret is None
