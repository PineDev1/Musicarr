from __future__ import annotations

import pytest
from fastapi import HTTPException, Response

from app.api import auth, settings as settings_api
from app.models import HistoryEvent
from app.models.schemas import AppLoginRequest, SettingsUpdate
from app.services.history import audit
from app.services.settings_service import ensure_settings


def _audits(db):
    return [e.message for e in db.query(HistoryEvent).filter(HistoryEvent.event_type == "audit")]


def test_audit_helper_formats_actor_and_detail(db):
    audit(db, "Thing happened", "detail", actor="riley")
    assert _audits(db) == ["Thing happened by riley: detail"]


def test_settings_change_logs_field_names_only(db):
    ensure_settings(db)
    settings_api.put_settings(SettingsUpdate(notify_on_complete=False), Response(), db)
    msgs = _audits(db)
    assert msgs == ["Settings changed: fields: notify_on_complete"]


def test_failed_login_audit_rows_are_capped_during_a_flood(db):
    row = ensure_settings(db)
    row.auth_enabled = True
    db.commit()
    for i in range(auth._FAILED_LOGIN_AUDIT_CAP + 15):
        with pytest.raises(HTTPException):
            auth.app_login(AppLoginRequest(username=f"bot{i}", password="x"), Response(), db)
    assert len(_audits(db)) == auth._FAILED_LOGIN_AUDIT_CAP


def test_failed_admin_login_is_audited_without_password(db):
    row = ensure_settings(db)
    row.auth_enabled = True
    db.commit()
    with pytest.raises(HTTPException) as e:
        auth.app_login(AppLoginRequest(username="mallory", password="hunter2hunter2"), Response(), db)
    assert e.value.status_code == 401
    msgs = _audits(db)
    assert msgs == ["Failed admin sign-in attempt for 'mallory'"]
    assert "hunter2" not in msgs[0]
