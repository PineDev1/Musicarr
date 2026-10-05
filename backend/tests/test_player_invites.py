from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException, Response

from app.api import player_invites as inv_api
from app.models import PlayerInvite, PlayerUser
from app.services import login_throttle, player_invites
from app.services.settings_service import ensure_settings


@pytest.fixture(autouse=True)
def _player_on(db, monkeypatch):
    row = ensure_settings(db)
    row.player_enabled = True
    db.commit()
    from app.services import settings_service

    settings_service.invalidate_settings_cache()
    monkeypatch.setattr(inv_api, "_require_admin", lambda request, db_: None)
    yield
    settings_service.invalidate_settings_cache()


def _accept(db, token, **kw):
    data = {"username": "newbie", "password": "longenough1", "display_name": "N"}
    data.update(kw)
    return inv_api.accept_invite(token, inv_api.InviteAccept(**data), None, Response(), db)


def test_token_is_shown_once_and_only_its_hash_is_stored(db):
    out = inv_api.admin_create_invite(inv_api.InviteCreate(note="for Sam"), None, db)
    row = db.get(PlayerInvite, out["id"])
    assert out["token"] not in row.token_hash and len(row.token_hash) == 64
    assert out["path"] == f"/player/invite/{out['token']}"
    assert "token" not in inv_api.admin_list_invites(None, db)[0]


def test_accepting_creates_the_account_signs_in_and_burns_the_invite(db):
    token = inv_api.admin_create_invite(inv_api.InviteCreate(), None, db)["token"]
    assert inv_api.check_invite(token, None, db)["valid"] is True
    resp = Response()
    status = inv_api.accept_invite(token, inv_api.InviteAccept(username="sam", password="longenough1", display_name="Sam"), None, resp, db)
    assert status.authenticated and status.username == "sam"
    assert "musicarr_player_session" in resp.headers["set-cookie"]
    assert db.query(PlayerUser).filter_by(username="sam").one().display_name == "Sam"
    with pytest.raises(HTTPException) as e:  # single use
        _accept(db, token, username="again")
    assert e.value.status_code == 400
    assert inv_api.admin_list_invites(None, db)[0]["status"] == "used"


def test_expired_and_unknown_tokens_look_identical(db):
    token = inv_api.admin_create_invite(inv_api.InviteCreate(), None, db)["token"]
    row = db.query(PlayerInvite).one()
    row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()
    msgs = []
    for t in (token, "nope-not-a-token"):
        with pytest.raises(HTTPException) as e:
            inv_api.check_invite(t, None, db)
        assert e.value.status_code == 404
        msgs.append(e.value.detail)
    assert msgs[0] == msgs[1]


def test_weak_password_or_taken_username_does_not_burn_the_invite(db):
    token = inv_api.admin_create_invite(inv_api.InviteCreate(), None, db)["token"]
    with pytest.raises(HTTPException):
        _accept(db, token, password="short")
    _accept(db, token, username="first")  # still works afterwards
    token2 = inv_api.admin_create_invite(inv_api.InviteCreate(), None, db)["token"]
    with pytest.raises(HTTPException) as e:
        _accept(db, token2, username="first")  # username already exists
    assert "exists" in e.value.detail
    assert player_invites.status_of(db.query(PlayerInvite).order_by(PlayerInvite.id.desc()).first()) == "pending"


def test_guessing_tokens_gets_throttled(db):
    for _ in range(login_throttle.MAX_PER_IP):
        with pytest.raises(HTTPException):
            inv_api.check_invite("guess", None, db)
    with pytest.raises(HTTPException) as e:
        inv_api.check_invite("guess", None, db)
    assert e.value.status_code == 429


def test_revoke_removes_the_invite(db):
    out = inv_api.admin_create_invite(inv_api.InviteCreate(), None, db)
    inv_api.admin_revoke_invite(out["id"], None, db)
    with pytest.raises(HTTPException):
        inv_api.check_invite(out["token"], None, db)
    with pytest.raises(HTTPException) as e:
        inv_api.admin_revoke_invite(out["id"], None, db)
    assert e.value.status_code == 404
