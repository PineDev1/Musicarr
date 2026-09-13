from __future__ import annotations

import mimetypes
import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.models import (
    Album,
    Artist,
    PlayerFavorite,
    PlayerPlayEvent,
    PlayerPlaylist,
    PlayerPlaylistTrack,
    Track,
)
from app.models.schemas import (
    PlayerAlbumOut,
    PlayerArtistOut,
    PlayerAuthStatus,
    PlayerCommandsOut,
    PlayerLoginRequest,
    PlayerNowPlayingOut,
    PlayerPasswordChange,
    PlayerPlayingUpdate,
    PlayerPlaylistAddTracks,
    PlayerPlaylistCreate,
    PlayerPlaylistOut,
    PlayerPlaylistUpdate,
    PlayerPrefsOut,
    PlayerPrefsUpdate,
    PlayerTrackOut,
    PlayerUserCreate,
    PlayerUserOut,
    PlayerUserUpdate,
)
from app.services import app_auth, player_auth, player_presence
from app.services.app_auth import hash_password, verify_password
from app.services.history import add_history

router = APIRouter(prefix="/player", tags=["player"])


def _require_player_enabled(db: Session) -> None:
    if not player_auth.player_enabled(db):
        raise HTTPException(status_code=404, detail="Player is disabled")


def _current_player_user(request: Request, db: Session):
    _require_player_enabled(db)
    user = player_auth.parse_session_token(db, request.cookies.get(player_auth.COOKIE_NAME))
    if not user:
        raise HTTPException(status_code=401, detail="Player authentication required")
    return user


def _require_admin(request: Request, db: Session) -> None:
    """Admin session if admin auth is on; otherwise open (LAN trust)."""
    if not app_auth.auth_enabled(db):
        return
    token = request.cookies.get(app_auth.COOKIE_NAME)
    if not app_auth.parse_session_token(db, token):
        raise HTTPException(status_code=401, detail="Admin authentication required")


def _format_from_path(path: str | None) -> str:
    if not path:
        return ""
    ext = Path(path).suffix.lower().lstrip(".")
    return ext


def _quality_for_track(track: Track) -> str:
    album = track.album
    q = (getattr(album, "quality", None) or "") if album else ""
    if q:
        return q.lower()
    fmt = _format_from_path(track.path)
    if fmt == "flac":
        return "flac"
    if fmt in {"mp3", "m4a", "aac"}:
        return "320"
    return fmt


def _track_out(track: Track) -> PlayerTrackOut:
    album = track.album
    artist = album.artist if album else None
    fmt = _format_from_path(track.path)
    return PlayerTrackOut(
        id=track.id,
        title=track.title,
        track_no=track.track_no or 0,
        disc_no=track.disc_no or 1,
        duration=track.duration or 0,
        album_id=track.album_id,
        album_title=album.title if album else "",
        artist_id=artist.id if artist else 0,
        artist_name=artist.name if artist else "",
        cover_url=album.cover_url if album else None,
        quality=_quality_for_track(track),
        format=fmt,
    )


def _downloaded_tracks_query():
    return (
        select(Track)
        .options(joinedload(Track.album).joinedload(Album.artist))
        .where(Track.path.is_not(None), Track.path != "")
    )


# ----- Auth -----


@router.get("/status", response_model=PlayerAuthStatus)
def status(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get(player_auth.COOKIE_NAME)
    return PlayerAuthStatus(**player_auth.auth_status(db, token))


@router.post("/login", response_model=PlayerAuthStatus)
def login(payload: PlayerLoginRequest, response: Response, db: Session = Depends(get_db)):
    _require_player_enabled(db)
    user = player_auth.authenticate(db, payload.username, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = player_auth.create_session_token(db, user)
    player_auth.set_session_cookie(response, token, db)
    return PlayerAuthStatus(**player_auth.auth_status(db, token))


@router.post("/logout", response_model=PlayerAuthStatus)
def logout(response: Response, db: Session = Depends(get_db)):
    player_auth.clear_session_cookie(response, db)
    return PlayerAuthStatus(
        enabled=player_auth.player_enabled(db),
        authenticated=False,
        username=None,
        user_id=None,
        display_name=None,
    )


@router.post("/me/password")
def change_password(
    payload: PlayerPasswordChange,
    request: Request,
    db: Session = Depends(get_db),
):
    user = _current_player_user(request, db)
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    user.password_hash = hash_password(payload.new_password.strip())
    db.commit()
    return {"ok": True}


# ----- Admin user CRUD -----


@router.get("/users", response_model=list[PlayerUserOut])
def admin_list_users(request: Request, db: Session = Depends(get_db)):
    _require_admin(request, db)
    return player_auth.list_users(db)


@router.post("/users", response_model=PlayerUserOut)
def admin_create_user(payload: PlayerUserCreate, request: Request, db: Session = Depends(get_db)):
    _require_admin(request, db)
    try:
        user = player_auth.create_user(
            db,
            username=payload.username,
            password=payload.password,
            display_name=payload.display_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    add_history(db, "player_user", f"Created player user {user.username}")
    return user


@router.patch("/users/{user_id}", response_model=PlayerUserOut)
def admin_update_user(
    user_id: int,
    payload: PlayerUserUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    _require_admin(request, db)
    try:
        return player_auth.update_user(
            db,
            user_id,
            password=payload.password,
            display_name=payload.display_name,
            is_active=payload.is_active,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404 if "not found" in str(exc).lower() else 400, detail=str(exc)) from exc


@router.delete("/users/{user_id}")
def admin_delete_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    _require_admin(request, db)
    try:
        player_auth.delete_user(db, user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True}


# ----- Catalog -----


@router.get("/artists", response_model=list[PlayerArtistOut])
def list_artists(request: Request, db: Session = Depends(get_db)):
    _current_player_user(request, db)
    tracks = db.scalars(_downloaded_tracks_query()).unique().all()
    by_artist: dict[int, PlayerArtistOut] = {}
    for t in tracks:
        album = t.album
        if not album or not album.artist:
            continue
        a = album.artist
        if a.id not in by_artist:
            by_artist[a.id] = PlayerArtistOut(
                id=a.id, name=a.name, image_url=a.image_url, album_count=0
            )
    # Count distinct downloaded albums per artist
    album_ids: dict[int, set[int]] = {}
    for t in tracks:
        if t.album and t.album.artist_id in by_artist:
            album_ids.setdefault(t.album.artist_id, set()).add(t.album_id)
    for aid, albums in album_ids.items():
        by_artist[aid].album_count = len(albums)
    return sorted(by_artist.values(), key=lambda x: x.name.lower())


@router.get("/artists/{artist_id}/albums", response_model=list[PlayerAlbumOut])
def artist_albums(artist_id: int, request: Request, db: Session = Depends(get_db)):
    _current_player_user(request, db)
    artist = db.get(Artist, artist_id)
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")
    albums = db.scalars(
        select(Album)
        .options(joinedload(Album.tracks), joinedload(Album.artist))
        .where(Album.artist_id == artist_id, Album.status == "downloaded")
    ).unique().all()
    out = []
    for album in albums:
        playable = [t for t in (album.tracks or []) if t.path]
        if not playable:
            continue
        out.append(
            PlayerAlbumOut(
                id=album.id,
                title=album.title,
                artist_id=artist.id,
                artist_name=artist.name,
                cover_url=album.cover_url,
                release_date=album.release_date,
                track_count=len(playable),
                quality=getattr(album, "quality", "") or "",
                tracks=[],
            )
        )
    return out


@router.get("/albums/{album_id}", response_model=PlayerAlbumOut)
def get_album(album_id: int, request: Request, db: Session = Depends(get_db)):
    _current_player_user(request, db)
    album = db.scalar(
        select(Album)
        .options(joinedload(Album.tracks), joinedload(Album.artist))
        .where(Album.id == album_id)
    )
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")
    tracks = [
        _track_out(t)
        for t in sorted(album.tracks or [], key=lambda x: (x.disc_no or 1, x.track_no or 0))
        if t.path
    ]
    return PlayerAlbumOut(
        id=album.id,
        title=album.title,
        artist_id=album.artist_id,
        artist_name=album.artist.name if album.artist else "",
        cover_url=album.cover_url,
        release_date=album.release_date,
        track_count=len(tracks),
        quality=getattr(album, "quality", "") or "",
        tracks=tracks,
    )


@router.get("/search", response_model=list[PlayerTrackOut])
def search(request: Request, q: str = "", db: Session = Depends(get_db)):
    _current_player_user(request, db)
    query = (q or "").strip().lower()
    if len(query) < 1:
        return []
    tracks = db.scalars(_downloaded_tracks_query()).unique().all()
    hits = []
    for t in tracks:
        album = t.album
        artist = album.artist if album else None
        blob = " ".join(
            [
                t.title or "",
                album.title if album else "",
                artist.name if artist else "",
            ]
        ).lower()
        if query in blob:
            hits.append(_track_out(t))
        if len(hits) >= 80:
            break
    return hits


@router.get("/stream/{track_id}")
def stream_track(track_id: int, request: Request, db: Session = Depends(get_db)):
    _current_player_user(request, db)
    track = db.scalar(
        select(Track).options(joinedload(Track.album)).where(Track.id == track_id)
    )
    if not track or not track.path:
        raise HTTPException(status_code=404, detail="Track not found")
    path = Path(track.path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Audio file missing on disk")

    media_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    if path.suffix.lower() == ".flac":
        media_type = "audio/flac"
    elif path.suffix.lower() == ".mp3":
        media_type = "audio/mpeg"
    elif path.suffix.lower() in {".m4a", ".aac"}:
        media_type = "audio/mp4"

    quality = _quality_for_track(track)
    file_size = path.stat().st_size
    range_header = request.headers.get("range")

    headers = {
        "Accept-Ranges": "bytes",
        "X-Musicarr-Quality": quality,
        "Cache-Control": "private, max-age=3600",
    }

    if range_header:
        match = re.match(r"bytes=(\d+)-(\d*)", range_header)
        if match:
            start = int(match.group(1))
            end = int(match.group(2)) if match.group(2) else file_size - 1
            end = min(end, file_size - 1)
            if start >= file_size or start > end:
                raise HTTPException(status_code=416, detail="Invalid range")
            length = end - start + 1

            def iter_file():
                with path.open("rb") as f:
                    f.seek(start)
                    remaining = length
                    while remaining > 0:
                        chunk = f.read(min(64 * 1024, remaining))
                        if not chunk:
                            break
                        remaining -= len(chunk)
                        yield chunk

            headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
            headers["Content-Length"] = str(length)
            return StreamingResponse(
                iter_file(),
                status_code=206,
                media_type=media_type,
                headers=headers,
            )

    return FileResponse(
        path,
        media_type=media_type,
        headers=headers,
        filename=path.name,
    )


# ----- Playlists -----


def _playlist_out(pl: PlayerPlaylist, *, include_tracks: bool = False) -> PlayerPlaylistOut:
    items = list(pl.tracks or [])
    tracks_out = []
    if include_tracks:
        for item in sorted(items, key=lambda x: x.position):
            if item.track and item.track.path:
                tracks_out.append(_track_out(item.track))
    return PlayerPlaylistOut(
        id=pl.id,
        name=pl.name,
        track_count=len([i for i in items if i.track and i.track.path]),
        created_at=pl.created_at,
        updated_at=pl.updated_at,
        tracks=tracks_out,
        is_smart=bool(getattr(pl, "is_smart", False)),
        builtin=False,
        kind=None,
    )


def _prefs_out(user) -> PlayerPrefsOut:
    return PlayerPrefsOut(
        show_recently_played=bool(getattr(user, "show_recently_played", True)),
        show_shuffle_mix=bool(getattr(user, "show_shuffle_mix", True)),
        wave_height=float(getattr(user, "wave_height", 6.0) or 6.0),
        wave_length=float(getattr(user, "wave_length", 20.0) or 20.0),
        wave_speed=float(getattr(user, "wave_speed", 12.0) or 12.0),
        wave_thickness=float(getattr(user, "wave_thickness", 3.0) or 3.0),
        wave_color=getattr(user, "wave_color", None) or "#3dba7a",
        wave_flatten_when_paused=bool(getattr(user, "wave_flatten_when_paused", True)),
    )


def _builtin_meta(kind: str, name: str, tracks: list[PlayerTrackOut]) -> PlayerPlaylistOut:
    now = datetime.now(timezone.utc)
    return PlayerPlaylistOut(
        id=kind,
        name=name,
        track_count=len(tracks),
        created_at=now,
        updated_at=now,
        tracks=tracks,
        is_smart=False,
        builtin=True,
        kind=kind,
    )


@router.get("/me/prefs", response_model=PlayerPrefsOut)
def get_prefs(request: Request, db: Session = Depends(get_db)):
    user = _current_player_user(request, db)
    return _prefs_out(user)


@router.patch("/me/prefs", response_model=PlayerPrefsOut)
def update_prefs(payload: PlayerPrefsUpdate, request: Request, db: Session = Depends(get_db)):
    user = _current_player_user(request, db)
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(user, key, value)
    db.commit()
    db.refresh(user)
    return _prefs_out(user)


@router.get("/favorites", response_model=list[PlayerTrackOut])
def list_favorites(request: Request, db: Session = Depends(get_db)):
    user = _current_player_user(request, db)
    rows = db.scalars(
        select(PlayerFavorite)
        .options(
            joinedload(PlayerFavorite.track)
            .joinedload(Track.album)
            .joinedload(Album.artist)
        )
        .where(PlayerFavorite.user_id == user.id)
        .order_by(PlayerFavorite.created_at.desc())
    ).unique().all()
    return [_track_out(r.track) for r in rows if r.track and r.track.path]


@router.get("/favorites/ids")
def favorite_ids(request: Request, db: Session = Depends(get_db)):
    user = _current_player_user(request, db)
    ids = db.scalars(
        select(PlayerFavorite.track_id).where(PlayerFavorite.user_id == user.id)
    ).all()
    return {"ids": list(ids)}


@router.post("/favorites/{track_id}", response_model=PlayerTrackOut)
def add_favorite(track_id: int, request: Request, db: Session = Depends(get_db)):
    user = _current_player_user(request, db)
    track = db.scalar(
        select(Track)
        .options(joinedload(Track.album).joinedload(Album.artist))
        .where(Track.id == track_id)
    )
    if not track or not track.path:
        raise HTTPException(status_code=404, detail="Track not found")
    existing = db.scalar(
        select(PlayerFavorite).where(
            PlayerFavorite.user_id == user.id, PlayerFavorite.track_id == track_id
        )
    )
    if not existing:
        db.add(
            PlayerFavorite(
                user_id=user.id,
                track_id=track_id,
                created_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
    return _track_out(track)


@router.delete("/favorites/{track_id}")
def remove_favorite(track_id: int, request: Request, db: Session = Depends(get_db)):
    user = _current_player_user(request, db)
    row = db.scalar(
        select(PlayerFavorite).where(
            PlayerFavorite.user_id == user.id, PlayerFavorite.track_id == track_id
        )
    )
    if row:
        db.delete(row)
        db.commit()
    return {"ok": True}

@router.post("/me/playing")
def report_playing(payload: PlayerPlayingUpdate, request: Request, db: Session = Depends(get_db)):
    user = _current_player_user(request, db)
    title = payload.title
    artist_name = payload.artist_name
    cover_url = payload.cover_url
    if payload.track_id:
        track = db.scalar(
            select(Track)
            .options(joinedload(Track.album).joinedload(Album.artist))
            .where(Track.id == payload.track_id)
        )
        if track:
            out = _track_out(track)
            title = title or out.title
            artist_name = artist_name or out.artist_name
            cover_url = cover_url or out.cover_url
            if payload.playing:
                last = db.scalar(
                    select(PlayerPlayEvent)
                    .where(
                        PlayerPlayEvent.user_id == user.id,
                        PlayerPlayEvent.track_id == payload.track_id,
                    )
                    .order_by(PlayerPlayEvent.played_at.desc())
                    .limit(1)
                )
                now = datetime.now(timezone.utc)
                if not last or (now - last.played_at).total_seconds() > 30:
                    db.add(
                        PlayerPlayEvent(
                            user_id=user.id,
                            track_id=payload.track_id,
                            played_at=now,
                        )
                    )
                    db.commit()
    player_presence.heartbeat(
        user_id=user.id,
        username=user.username,
        display_name=user.display_name or user.username,
        track_id=payload.track_id,
        title=title,
        artist_name=artist_name,
        cover_url=cover_url,
        playing=payload.playing,
        position=payload.position,
    )
    return {"ok": True}


@router.get("/me/commands", response_model=PlayerCommandsOut)
def get_commands(request: Request, db: Session = Depends(get_db)):
    user = _current_player_user(request, db)
    stop = player_presence.pop_stop(user.id)
    return PlayerCommandsOut(stop=stop)


@router.get("/admin/now-playing", response_model=list[PlayerNowPlayingOut])
def admin_now_playing(request: Request, db: Session = Depends(get_db)):
    _require_admin(request, db)
    return [
        PlayerNowPlayingOut(
            user_id=e.user_id,
            username=e.username,
            display_name=e.display_name,
            track_id=e.track_id,
            title=e.title,
            artist_name=e.artist_name,
            cover_url=e.cover_url,
            playing=e.playing,
            position=e.position,
            updated_at=e.updated_at,
        )
        for e in player_presence.list_active()
        if e.username
    ]


@router.post("/admin/now-playing/{user_id}/stop")
def admin_stop_playing(user_id: int, request: Request, db: Session = Depends(get_db)):
    _require_admin(request, db)
    player_presence.request_stop(user_id)
    return {"ok": True}


def _tracks_liked(db: Session, user_id: int) -> list[PlayerTrackOut]:
    rows = db.scalars(
        select(PlayerFavorite)
        .options(
            joinedload(PlayerFavorite.track)
            .joinedload(Track.album)
            .joinedload(Album.artist)
        )
        .where(PlayerFavorite.user_id == user_id)
        .order_by(PlayerFavorite.created_at.desc())
    ).unique().all()
    return [_track_out(r.track) for r in rows if r.track and r.track.path]


def _tracks_recently_added(db: Session, limit: int = 100) -> list[PlayerTrackOut]:
    rows = db.scalars(
        _downloaded_tracks_query().order_by(Track.id.desc()).limit(limit)
    ).unique().all()
    return [_track_out(t) for t in rows]


def _tracks_recently_played(db: Session, user_id: int, limit: int = 100) -> list[PlayerTrackOut]:
    events = db.scalars(
        select(PlayerPlayEvent)
        .options(
            joinedload(PlayerPlayEvent.track)
            .joinedload(Track.album)
            .joinedload(Album.artist)
        )
        .where(PlayerPlayEvent.user_id == user_id)
        .order_by(PlayerPlayEvent.played_at.desc())
        .limit(limit * 3)
    ).unique().all()
    seen: set[int] = set()
    out: list[PlayerTrackOut] = []
    for ev in events:
        if not ev.track or not ev.track.path or ev.track_id in seen:
            continue
        seen.add(ev.track_id)
        out.append(_track_out(ev.track))
        if len(out) >= limit:
            break
    return out


def _tracks_shuffle_mix(db: Session, limit: int = 50) -> list[PlayerTrackOut]:
    rows = list(db.scalars(_downloaded_tracks_query().limit(500)).unique().all())
    import random

    random.shuffle(rows)
    return [_track_out(t) for t in rows[:limit]]


@router.get("/library/builtins", response_model=list[PlayerPlaylistOut])
def list_builtins(request: Request, db: Session = Depends(get_db)):
    user = _current_player_user(request, db)
    prefs = _prefs_out(user)
    items = [
        _builtin_meta("liked", "Liked Songs", _tracks_liked(db, user.id)),
        _builtin_meta("recently-added", "Recently Added", _tracks_recently_added(db)),
    ]
    if prefs.show_recently_played:
        items.append(
            _builtin_meta("recently-played", "Recently Played", _tracks_recently_played(db, user.id))
        )
    if prefs.show_shuffle_mix:
        items.append(_builtin_meta("shuffle-mix", "Shuffle Mix", _tracks_shuffle_mix(db)))
    return items


@router.get("/library/builtins/{kind}", response_model=PlayerPlaylistOut)
def get_builtin(kind: str, request: Request, db: Session = Depends(get_db)):
    user = _current_player_user(request, db)
    prefs = _prefs_out(user)
    mapping = {
        "liked": ("Liked Songs", lambda: _tracks_liked(db, user.id)),
        "recently-added": ("Recently Added", lambda: _tracks_recently_added(db)),
        "recently-played": ("Recently Played", lambda: _tracks_recently_played(db, user.id)),
        "shuffle-mix": ("Shuffle Mix", lambda: _tracks_shuffle_mix(db)),
    }
    if kind not in mapping:
        raise HTTPException(status_code=404, detail="Unknown built-in playlist")
    if kind == "recently-played" and not prefs.show_recently_played:
        raise HTTPException(status_code=404, detail="Recently Played is disabled")
    if kind == "shuffle-mix" and not prefs.show_shuffle_mix:
        raise HTTPException(status_code=404, detail="Shuffle Mix is disabled")
    name, loader = mapping[kind]
    return _builtin_meta(kind, name, loader())


# ----- Playlists -----


@router.get("/playlists", response_model=list[PlayerPlaylistOut])
def list_playlists(request: Request, db: Session = Depends(get_db)):
    user = _current_player_user(request, db)
    rows = db.scalars(
        select(PlayerPlaylist)
        .options(joinedload(PlayerPlaylist.tracks).joinedload(PlayerPlaylistTrack.track))
        .where(PlayerPlaylist.user_id == user.id)
        .order_by(PlayerPlaylist.name)
    ).unique().all()
    return [_playlist_out(p) for p in rows]


@router.post("/playlists", response_model=PlayerPlaylistOut)
def create_playlist(
    payload: PlayerPlaylistCreate, request: Request, db: Session = Depends(get_db)
):
    user = _current_player_user(request, db)
    now = datetime.now(timezone.utc)
    pl = PlayerPlaylist(
        user_id=user.id,
        name=payload.name.strip(),
        is_smart=bool(payload.is_smart),
        created_at=now,
        updated_at=now,
    )
    db.add(pl)
    db.commit()
    db.refresh(pl)
    return _playlist_out(pl)


@router.get("/playlists/{playlist_id}", response_model=PlayerPlaylistOut)
def get_playlist(playlist_id: int, request: Request, db: Session = Depends(get_db)):
    user = _current_player_user(request, db)
    pl = db.scalar(
        select(PlayerPlaylist)
        .options(
            joinedload(PlayerPlaylist.tracks)
            .joinedload(PlayerPlaylistTrack.track)
            .joinedload(Track.album)
            .joinedload(Album.artist)
        )
        .where(PlayerPlaylist.id == playlist_id, PlayerPlaylist.user_id == user.id)
    )
    if not pl:
        raise HTTPException(status_code=404, detail="Playlist not found")
    return _playlist_out(pl, include_tracks=True)


@router.patch("/playlists/{playlist_id}", response_model=PlayerPlaylistOut)
def update_playlist(
    playlist_id: int,
    payload: PlayerPlaylistUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    user = _current_player_user(request, db)
    pl = db.scalar(
        select(PlayerPlaylist).where(
            PlayerPlaylist.id == playlist_id, PlayerPlaylist.user_id == user.id
        )
    )
    if not pl:
        raise HTTPException(status_code=404, detail="Playlist not found")
    if payload.name is not None:
        pl.name = payload.name.strip()
    if payload.is_smart is not None:
        pl.is_smart = payload.is_smart
    pl.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(pl)
    return _playlist_out(pl)


@router.delete("/playlists/{playlist_id}")
def delete_playlist(playlist_id: int, request: Request, db: Session = Depends(get_db)):
    user = _current_player_user(request, db)
    pl = db.scalar(
        select(PlayerPlaylist).where(
            PlayerPlaylist.id == playlist_id, PlayerPlaylist.user_id == user.id
        )
    )
    if not pl:
        raise HTTPException(status_code=404, detail="Playlist not found")
    db.delete(pl)
    db.commit()
    return {"ok": True}


@router.post("/playlists/{playlist_id}/tracks", response_model=PlayerPlaylistOut)
def add_tracks(
    playlist_id: int,
    payload: PlayerPlaylistAddTracks,
    request: Request,
    db: Session = Depends(get_db),
):
    user = _current_player_user(request, db)
    pl = db.scalar(
        select(PlayerPlaylist)
        .options(joinedload(PlayerPlaylist.tracks))
        .where(PlayerPlaylist.id == playlist_id, PlayerPlaylist.user_id == user.id)
    )
    if not pl:
        raise HTTPException(status_code=404, detail="Playlist not found")
    existing = {i.track_id for i in (pl.tracks or [])}
    pos = max((i.position for i in (pl.tracks or [])), default=-1) + 1
    for tid in payload.track_ids:
        if tid in existing:
            continue
        track = db.get(Track, tid)
        if not track or not track.path:
            continue
        db.add(PlayerPlaylistTrack(playlist_id=pl.id, track_id=tid, position=pos))
        pos += 1
        existing.add(tid)
    pl.updated_at = datetime.now(timezone.utc)
    db.commit()
    return get_playlist(playlist_id, request, db)


@router.delete("/playlists/{playlist_id}/tracks/{track_id}")
def remove_track(
    playlist_id: int, track_id: int, request: Request, db: Session = Depends(get_db)
):
    user = _current_player_user(request, db)
    pl = db.scalar(
        select(PlayerPlaylist).where(
            PlayerPlaylist.id == playlist_id, PlayerPlaylist.user_id == user.id
        )
    )
    if not pl:
        raise HTTPException(status_code=404, detail="Playlist not found")
    row = db.scalar(
        select(PlayerPlaylistTrack).where(
            PlayerPlaylistTrack.playlist_id == playlist_id,
            PlayerPlaylistTrack.track_id == track_id,
        )
    )
    if row:
        db.delete(row)
        pl.updated_at = datetime.now(timezone.utc)
        db.commit()
    return {"ok": True}


@router.get("/playlists/{playlist_id}/suggestions", response_model=list[PlayerTrackOut])
def playlist_suggestions(
    playlist_id: int, request: Request, db: Session = Depends(get_db)
):
    user = _current_player_user(request, db)
    pl = db.scalar(
        select(PlayerPlaylist)
        .options(
            joinedload(PlayerPlaylist.tracks)
            .joinedload(PlayerPlaylistTrack.track)
            .joinedload(Track.album)
            .joinedload(Album.artist)
        )
        .where(PlayerPlaylist.id == playlist_id, PlayerPlaylist.user_id == user.id)
    )
    if not pl:
        raise HTTPException(status_code=404, detail="Playlist not found")
    if not pl.is_smart:
        raise HTTPException(status_code=400, detail="Playlist is not smart")
    seed_tracks = [i.track for i in (pl.tracks or []) if i.track and i.track.path]
    if len(seed_tracks) < 10:
        raise HTTPException(
            status_code=400,
            detail="Add at least 10 songs to unlock suggestions",
        )
    existing_ids = {t.id for t in seed_tracks}
    artist_ids = {t.album.artist_id for t in seed_tracks if t.album and t.album.artist_id}
    album_ids = {t.album_id for t in seed_tracks}

    candidates_q = _downloaded_tracks_query().limit(800)
    candidates = db.scalars(candidates_q).unique().all()

    scored: list[tuple[int, Track]] = []
    for t in candidates:
        if t.id in existing_ids:
            continue
        score = 0
        if t.album and t.album.artist_id in artist_ids:
            score += 30
        if t.album_id in album_ids:
            score += 20
        fmt = _format_from_path(t.path)
        if any(_format_from_path(s.path) == fmt for s in seed_tracks[:5]):
            score += 5
        if score > 0:
            scored.append((score, t))
    scored.sort(key=lambda x: (-x[0], x[1].id))
    return [_track_out(t) for _, t in scored[:30]]
