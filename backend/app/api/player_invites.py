from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.player import _require_admin, _require_player_enabled
from app.core.database import get_db
from app.models.schemas import PlayerAuthStatus
from app.services import login_throttle, player_auth, player_invites
from app.services.server_tools import iso_utc
from app.services.history import add_history, audit

router = APIRouter(prefix="/player", tags=["player-invites"])


class InviteCreate(BaseModel):
    note: str = Field(default="", max_length=128)
    days: int = Field(default=player_invites.DEFAULT_DAYS, ge=1, le=player_invites.MAX_DAYS)


class InviteAccept(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=256)
    display_name: str = Field(default="", max_length=128)


def _out(row) -> dict:
    return {
        "id": row.id,
        "note": row.note,
        "status": player_invites.status_of(row),
        "created_at": iso_utc(row.created_at),
        "expires_at": iso_utc(row.expires_at),
        "used_by_user_id": row.used_by_user_id,
    }


# ---- admin (gated by the /api/player/admin prefix + _require_admin) ----


@router.get("/admin/invites")
def admin_list_invites(request: Request, db: Session = Depends(get_db)):
    _require_admin(request, db)
    return [_out(r) for r in player_invites.list_invites(db)]


@router.post("/admin/invites")
def admin_create_invite(payload: InviteCreate, request: Request, db: Session = Depends(get_db)):
    _require_admin(request, db)
    raw, row = player_invites.create_invite(db, note=payload.note, days=payload.days)
    audit(db, "Player invite created", payload.note or f"id {row.id}")
    # The token is shown exactly once; only its hash is stored.
    return {**_out(row), "token": raw, "path": f"/player/invite/{raw}"}


@router.delete("/admin/invites/{invite_id}")
def admin_revoke_invite(invite_id: int, request: Request, db: Session = Depends(get_db)):
    _require_admin(request, db)
    try:
        player_invites.revoke(db, invite_id)
    except player_invites.InviteError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    audit(db, "Player invite revoked", f"id {invite_id}")
    return {"ok": True}


# ---- public (the invite token is the credential) ----


@router.get("/invite/{token}")
def check_invite(token: str, request: Request, db: Session = Depends(get_db)):
    _require_player_enabled(db)
    login_throttle.enforce("invite", request, "")
    try:
        row = player_invites.find_usable(db, token)
    except player_invites.InviteError as exc:
        login_throttle.record_failure("invite", login_throttle.client_ip(request), "")
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"valid": True, "note": row.note, "expires_at": iso_utc(row.expires_at)}


@router.post("/invite/{token}/accept", response_model=PlayerAuthStatus)
def accept_invite(
    token: str,
    payload: InviteAccept,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    _require_player_enabled(db)
    login_throttle.enforce("invite", request, "")
    try:
        user = player_invites.accept(
            db, token, username=payload.username, password=payload.password, display_name=payload.display_name
        )
    except player_invites.InviteError as exc:
        # Counts toward the throttle so tokens can't be brute-forced.
        login_throttle.record_failure("invite", login_throttle.client_ip(request), "")
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    add_history(db, "player_user", f"Created player user {user.username} from an invite")
    session = player_auth.create_session_token(db, user)
    player_auth.set_session_cookie(response, session, db)
    return PlayerAuthStatus(**player_auth.auth_status(db, session))
