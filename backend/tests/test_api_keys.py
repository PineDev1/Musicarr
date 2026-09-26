from __future__ import annotations

from app.services import api_keys


def test_create_and_verify_key(db):
    raw, row = api_keys.create_key(db, name="Overseerr")
    assert raw.startswith(api_keys.KEY_PREFIX)
    assert row.key_prefix == raw[: len(api_keys.KEY_PREFIX) + 6]

    found = api_keys.verify_key(db, raw)
    assert found is not None
    assert found.id == row.id
    assert found.last_used_at is not None


def test_verify_key_rejects_wrong_key(db):
    api_keys.create_key(db, name="Overseerr")
    assert api_keys.verify_key(db, "mcr_not-a-real-key") is None
    assert api_keys.verify_key(db, None) is None
    assert api_keys.verify_key(db, "") is None


def test_verify_key_rejects_revoked_key(db):
    raw, row = api_keys.create_key(db, name="Overseerr")
    api_keys.revoke_key(db, row.id)
    assert api_keys.verify_key(db, raw) is None


def test_verify_key_rejects_disabled_key(db):
    raw, row = api_keys.create_key(db, name="Overseerr")
    row.enabled = False
    db.commit()
    assert api_keys.verify_key(db, raw) is None


def test_create_key_requires_name(db):
    import pytest

    with pytest.raises(ValueError):
        api_keys.create_key(db, name="")
