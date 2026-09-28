from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.api.player import (
    _accessible_playlist,
    _avatar_url,
    _collaborators_out,
    _current_player_user,
    _track_out,
)
from app.core.database import get_db
from app.models import (
    Album,
    PlayerFavorite,
    PlayerFollow,
    PlayerPlayEvent,
    PlayerPlaylist,
    PlayerPlaylistMember,
    PlayerUser,
    Track,
)
from app.models.schemas import PlayerCollaboratorOut, PlayerTrackOut

router = APIRouter(prefix="/player/social", tags=["player-social"])


class PlayerPersonOut(BaseModel):
    id: int
    username: str
    display_name: str = ""
    avatar_url: str | None = None
    is_following: bool = False
    follows_you: bool = False


class PlayerProfileOut(PlayerPersonOut):
    followers: int = 0
    following: int = 0
    favorites: int = 0
    plays_30d: int = 0
    is_self: bool = False
    activity_shared: bool = False
    recent: list[PlayerTrackOut] = []


class AddCollaborator(BaseModel):
    username: str = Field(min_length=1, max_length=128)


def _person(u: PlayerUser, following: set[int], followers: set[int]) -> PlayerPersonOut:
    return PlayerPersonOut(
        id=u.id,
        username=u.username,
        display_name=u.display_name or "",
        avatar_url=_avatar_url(u),
        is_following=u.id in following,
        follows_you=u.id in followers,
    )


def _follow_sets(db: Session, user_id: int) -> tuple[set[int], set[int]]:
    following = set(
        db.scalars(select(PlayerFollow.followee_id).where(PlayerFollow.follower_id == user_id))
    )
    followers = set(
        db.scalars(select(PlayerFollow.follower_id).where(PlayerFollow.followee_id == user_id))
    )
    return following, followers


@router.get("/people", response_model=list[PlayerPersonOut])
def list_people(request: Request, db: Session = Depends(get_db)):
    user = _current_player_user(request, db)
    following, followers = _follow_sets(db, user.id)
    rows = db.scalars(
        select(PlayerUser)
        .where(PlayerUser.is_active.is_(True), PlayerUser.id != user.id)
        .order_by(PlayerUser.username)
    ).all()
    return [_person(u, following, followers) for u in rows]


@router.post("/follow/{user_id}")
def follow(user_id: int, request: Request, db: Session = Depends(get_db)):
    user = _current_player_user(request, db)
    if user_id == user.id:
        raise HTTPException(status_code=400, detail="You can't follow yourself")
    target = db.get(PlayerUser, user_id)
    if not target or not target.is_active:
        raise HTTPException(status_code=404, detail="User not found")
    exists = db.scalar(
        select(PlayerFollow.id).where(
            PlayerFollow.follower_id == user.id, PlayerFollow.followee_id == user_id
        )
    )
    if exists is None:
        db.add(PlayerFollow(follower_id=user.id, followee_id=user_id))
        db.commit()
    return {"ok": True}


@router.delete("/follow/{user_id}")
def unfollow(user_id: int, request: Request, db: Session = Depends(get_db)):
    user = _current_player_user(request, db)
    row = db.scalar(
        select(PlayerFollow).where(
            PlayerFollow.follower_id == user.id, PlayerFollow.followee_id == user_id
        )
    )
    if row:
        db.delete(row)
        db.commit()
    return {"ok": True}


@router.get("/profile/{user_id}", response_model=PlayerProfileOut)
def profile(user_id: int, request: Request, db: Session = Depends(get_db)):
    viewer = _current_player_user(request, db)
    u = db.get(PlayerUser, user_id)
    if not u or not u.is_active:
        raise HTTPException(status_code=404, detail="User not found")
    following, followers = _follow_sets(db, viewer.id)
    base = _person(u, following, followers)
    is_self = u.id == viewer.id
    shared = bool(u.share_listening_activity) or is_self
    since = datetime.now(timezone.utc) - timedelta(days=30)
    recent: list[PlayerTrackOut] = []
    if shared:
        events = db.scalars(
            select(PlayerPlayEvent)
            .options(
                joinedload(PlayerPlayEvent.track)
                .joinedload(Track.album)
                .joinedload(Album.artist)
            )
            .where(PlayerPlayEvent.user_id == u.id)
            .order_by(PlayerPlayEvent.played_at.desc())
            .limit(10)
        ).unique().all()
        recent = [_track_out(e.track) for e in events if e.track and e.track.path]
    return PlayerProfileOut(
        **base.model_dump(),
        followers=db.scalar(
            select(func.count()).select_from(PlayerFollow).where(PlayerFollow.followee_id == u.id)
        )
        or 0,
        following=db.scalar(
            select(func.count()).select_from(PlayerFollow).where(PlayerFollow.follower_id == u.id)
        )
        or 0,
        favorites=(
            db.scalar(
                select(func.count())
                .select_from(PlayerFavorite)
                .where(PlayerFavorite.user_id == u.id)
            )
            or 0
        )
        if shared
        else 0,
        plays_30d=(
            db.scalar(
                select(func.count())
                .select_from(PlayerPlayEvent)
                .where(PlayerPlayEvent.user_id == u.id, PlayerPlayEvent.played_at >= since)
            )
            or 0
        )
        if shared
        else 0,
        is_self=is_self,
        activity_shared=shared,
        recent=recent,
    )


@router.post("/playlists/{playlist_id}/collaborators", response_model=list[PlayerCollaboratorOut])
def add_collaborator(
    playlist_id: int, payload: AddCollaborator, request: Request, db: Session = Depends(get_db)
):
    user = _current_player_user(request, db)
    pl = _accessible_playlist(db, playlist_id, user, owner_only=True)
    if pl.is_smart:
        raise HTTPException(status_code=400, detail="Smart playlists can't be shared for editing")
    target = db.scalar(
        select(PlayerUser).where(
            func.lower(PlayerUser.username) == payload.username.strip().lower(),
            PlayerUser.is_active.is_(True),
        )
    )
    if not target:
        raise HTTPException(status_code=404, detail="No such user")
    if target.id == user.id:
        raise HTTPException(status_code=400, detail="You already own this playlist")
    exists = db.scalar(
        select(PlayerPlaylistMember.id).where(
            PlayerPlaylistMember.playlist_id == pl.id, PlayerPlaylistMember.user_id == target.id
        )
    )
    if exists is None:
        db.add(PlayerPlaylistMember(playlist_id=pl.id, user_id=target.id))
        db.commit()
    return _collaborators_out(db, pl)


@router.delete("/playlists/{playlist_id}/collaborators/{user_id}")
def remove_collaborator(
    playlist_id: int, user_id: int, request: Request, db: Session = Depends(get_db)
):
    user = _current_player_user(request, db)
    pl = _accessible_playlist(db, playlist_id, user)
    if pl.user_id != user.id and user_id != user.id:
        raise HTTPException(status_code=403, detail="Only the owner can remove others")
    row = db.scalar(
        select(PlayerPlaylistMember).where(
            PlayerPlaylistMember.playlist_id == pl.id, PlayerPlaylistMember.user_id == user_id
        )
    )
    if row:
        db.delete(row)
        db.commit()
    return {"ok": True}


@router.post("/playlists/{playlist_id}/leave")
def leave_playlist(playlist_id: int, request: Request, db: Session = Depends(get_db)):
    user = _current_player_user(request, db)
    row = db.scalar(
        select(PlayerPlaylistMember).where(
            PlayerPlaylistMember.playlist_id == playlist_id,
            PlayerPlaylistMember.user_id == user.id,
        )
    )
    if not row:
        raise HTTPException(status_code=404, detail="You're not a collaborator on this playlist")
    db.delete(row)
    db.commit()
    return {"ok": True}
