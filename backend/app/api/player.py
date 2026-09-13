from __future__ import annotations

import json
import mimetypes
import re
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Union

from mutagen import File as MutagenFile
from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings as app_config
from app.core.database import get_db
from app.models import (
    Album,
    Artist,
    PlayerFavorite,
    PlayerPlayEvent,
    PlayerPlaylist,
    PlayerPlaylistTrack,
    PlayerShareLink,
    PlayerUser,
    Track,
)
from app.models.schemas import (
    PlayerAlbumOut,
    PlayerArtistDetailOut,
    PlayerArtistOut,
    PlayerAuthStatus,
    PlayerCommandsOut,
    PlayerContinueOut,
    PlayerLibrarySongsPage,
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
    PlayerSearchGroupedOut,
    PlayerShareCreate,
    PlayerShareOut,
    PlayerSharePublicOut,
    PlayerTrackOut,
    PlayerUserCreate,
    PlayerUserOut,
    PlayerUserUpdate,
)
from app.services import app_auth, player_auth, player_presence
from app.services.app_auth import hash_password, verify_password
from app.services.history import add_history
from app.services.settings_service import ensure_settings

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


def _file_duration_seconds(path: str | None) -> int:
    if not path:
        return 0
    try:
        audio = MutagenFile(path)
        length = getattr(getattr(audio, "info", None), "length", None)
        if length and length > 0:
            return int(round(float(length)))
    except Exception:  # noqa: BLE001
        pass
    return 0


def _ensure_track_duration(track: Track) -> int:
    """Return duration seconds; fill from file tags when DB value is missing."""
    if track.duration and track.duration > 0:
        return int(track.duration)
    dur = _file_duration_seconds(track.path)
    if dur > 0:
        track.duration = dur
    return dur


def _track_out(track: Track) -> PlayerTrackOut:
    album = track.album
    artist = album.artist if album else None
    fmt = _format_from_path(track.path)
    return PlayerTrackOut(
        id=track.id,
        title=track.title,
        track_no=track.track_no or 0,
        disc_no=track.disc_no or 1,
        duration=_ensure_track_duration(track),
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


def _album_out(album: Album, *, include_tracks: bool = False) -> PlayerAlbumOut:
    artist = album.artist
    tracks_out: list[PlayerTrackOut] = []
    if include_tracks:
        for t in sorted(
            album.tracks or [],
            key=lambda x: (x.disc_no or 1, x.track_no or 0),
        ):
            if t.path:
                tracks_out.append(_track_out(t))
        playable_count = len(tracks_out)
    else:
        playable_count = len([t for t in (album.tracks or []) if t.path])
    return PlayerAlbumOut(
        id=album.id,
        title=album.title,
        artist_id=album.artist_id,
        artist_name=artist.name if artist else "",
        cover_url=album.cover_url,
        release_date=album.release_date,
        track_count=playable_count,
        quality=getattr(album, "quality", "") or "",
        tracks=tracks_out,
    )


def _avatar_url(user: PlayerUser | None) -> str | None:
    return player_auth.avatar_url_for_user(user)


def _sharing_enabled(db: Session) -> bool:
    return bool(getattr(ensure_settings(db), "player_sharing_enabled", True))


def _stream_file_response(track: Track, request: Request):
    if not track.path:
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


def _require_player_or_admin(request: Request, db: Session) -> None:
    _require_player_enabled(db)
    if player_auth.parse_session_token(db, request.cookies.get(player_auth.COOKIE_NAME)):
        return
    if not app_auth.auth_enabled(db):
        return
    token = request.cookies.get(app_auth.COOKIE_NAME)
    if app_auth.parse_session_token(db, token):
        return
    raise HTTPException(status_code=401, detail="Authentication required")


def _artist_downloaded_albums(db: Session, artist_id: int) -> list[Album]:
    albums = db.scalars(
        select(Album)
        .options(joinedload(Album.tracks), joinedload(Album.artist))
        .where(Album.artist_id == artist_id, Album.status == "downloaded")
    ).unique().all()
    return [a for a in albums if any(t.path for t in (a.tracks or []))]


def _sort_albums_newest(albums: list[Album]) -> list[Album]:
    return sorted(
        albums,
        key=lambda a: (a.release_date or "", a.id),
        reverse=True,
    )


def _top_songs_for_artist(
    db: Session,
    artist_id: int,
    user_id: int,
    *,
    limit: int = 8,
    featured: Album | None = None,
) -> list[PlayerTrackOut]:
    def play_counts(for_user: int | None) -> list[tuple[int, int]]:
        stmt = (
            select(PlayerPlayEvent.track_id, func.count(PlayerPlayEvent.id))
            .join(Track, Track.id == PlayerPlayEvent.track_id)
            .join(Album, Album.id == Track.album_id)
            .where(
                Album.artist_id == artist_id,
                Track.path.is_not(None),
                Track.path != "",
            )
        )
        if for_user is not None:
            stmt = stmt.where(PlayerPlayEvent.user_id == for_user)
        stmt = (
            stmt.group_by(PlayerPlayEvent.track_id)
            .order_by(func.count(PlayerPlayEvent.id).desc())
            .limit(limit)
        )
        return list(db.execute(stmt).all())

    rows = play_counts(user_id)
    seen = {r[0] for r in rows}
    if len(rows) < limit:
        for tid, _cnt in play_counts(None):
            if tid in seen:
                continue
            rows.append((tid, 0))
            seen.add(tid)
            if len(rows) >= limit:
                break

    track_ids = [r[0] for r in rows]
    if len(track_ids) < limit and featured:
        for t in sorted(
            featured.tracks or [],
            key=lambda x: (x.disc_no or 1, x.track_no or 0),
        ):
            if t.path and t.id not in seen:
                track_ids.append(t.id)
                seen.add(t.id)
            if len(track_ids) >= limit:
                break

    if not track_ids:
        return []

    tracks = db.scalars(
        select(Track)
        .options(joinedload(Track.album).joinedload(Album.artist))
        .where(Track.id.in_(track_ids))
    ).unique().all()
    by_id = {t.id: t for t in tracks}
    return [_track_out(by_id[tid]) for tid in track_ids if tid in by_id]


def _essential_albums(albums: list[Album], limit: int = 6) -> list[Album]:
    def rank(a: Album) -> tuple[int, int]:
        q = (getattr(a, "quality", "") or "").lower()
        flac = 1 if q == "flac" else 0
        tc = len([t for t in (a.tracks or []) if t.path])
        return (flac, tc)

    return sorted(albums, key=rank, reverse=True)[:limit]


def _parse_pinned_ids(raw: str | None) -> list[int]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [int(x) for x in data]
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return []


def _share_out(link: PlayerShareLink, request: Request) -> PlayerShareOut:
    track = link.track
    album = track.album if track else None
    artist = album.artist if album else None
    rel = f"/s/{link.token}"
    from app.services.proxy import public_domain, request_is_https
    from app.core.database import SessionLocal

    # Prefer the Host the browser used (includes port, e.g. localhost:8787).
    host = (request.headers.get("host") or "").strip()
    scheme = request.url.scheme or "http"
    db = SessionLocal()
    try:
        if request_is_https(request, db):
            scheme = "https"
        domain = public_domain(db)
        if domain:
            host = domain
    finally:
        db.close()
    base = f"{scheme}://{host}".rstrip("/") if host else str(request.base_url).rstrip("/")
    return PlayerShareOut(
        token=link.token,
        url=f"{base}{rel}",
        expires_at=link.expires_at,
        track_title=track.title if track else "",
        artist_name=artist.name if artist else "",
        cover_url=album.cover_url if album else None,
        play_count=int(link.play_count or 0),
        revoked=bool(link.revoked),
        created_at=link.created_at,
    )


def _valid_share(link: PlayerShareLink | None) -> PlayerShareLink:
    if not link or link.revoked:
        raise HTTPException(status_code=404, detail="Share link not found")
    now = datetime.now(timezone.utc)
    exp = link.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp < now:
        raise HTTPException(status_code=404, detail="Share link expired")
    return link


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
    return [player_auth.player_user_out(u) for u in player_auth.list_users(db)]


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
    return player_auth.player_user_out(user)


@router.patch("/users/{user_id}", response_model=PlayerUserOut)
def admin_update_user(
    user_id: int,
    payload: PlayerUserUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    _require_admin(request, db)
    try:
        user = player_auth.update_user(
            db,
            user_id,
            password=payload.password,
            display_name=payload.display_name,
            is_active=payload.is_active,
        )
        return player_auth.player_user_out(user)
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


@router.get("/artists/{artist_id}", response_model=PlayerArtistDetailOut)
def get_artist_detail(artist_id: int, request: Request, db: Session = Depends(get_db)):
    user = _current_player_user(request, db)
    artist = db.get(Artist, artist_id)
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")
    albums = _artist_downloaded_albums(db, artist_id)
    sorted_albums = _sort_albums_newest(albums)
    featured = sorted_albums[0] if sorted_albums else None
    top_songs = _top_songs_for_artist(
        db, artist_id, user.id, featured=featured
    )
    essential = _essential_albums(albums)
    db.commit()
    return PlayerArtistDetailOut(
        id=artist.id,
        name=artist.name,
        image_url=artist.image_url,
        album_count=len(albums),
        featured_album=_album_out(featured) if featured else None,
        top_songs=top_songs,
        essential_albums=[_album_out(a) for a in essential],
        albums=[_album_out(a) for a in sorted_albums],
    )


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
    db.commit()
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


def _search_hits(db: Session, query: str) -> list[Track]:
    tracks = db.scalars(_downloaded_tracks_query()).unique().all()
    hits: list[Track] = []
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
            hits.append(t)
        if len(hits) >= 80:
            break
    return hits


@router.get("/search", response_model=Union[list[PlayerTrackOut], PlayerSearchGroupedOut])
def search(
    request: Request,
    q: str = "",
    grouped: int = 0,
    db: Session = Depends(get_db),
):
    _current_player_user(request, db)
    query = (q or "").strip().lower()
    if len(query) < 1:
        return [] if not grouped else PlayerSearchGroupedOut()
    hits = _search_hits(db, query)
    if not grouped:
        out = [_track_out(t) for t in hits]
        db.commit()
        return out

    songs = [_track_out(t) for t in hits[:40]]
    top = songs[0] if songs else None

    album_ids: set[int] = set()
    artist_ids: set[int] = set()
    albums_out: list[PlayerAlbumOut] = []
    artists_out: list[PlayerArtistOut] = []
    for t in hits:
        album = t.album
        if album and album.id not in album_ids:
            album_ids.add(album.id)
            albums_out.append(_album_out(album))
        artist = album.artist if album else None
        if artist and artist.id not in artist_ids:
            artist_ids.add(artist.id)
            dl_albums = _artist_downloaded_albums(db, artist.id)
            artists_out.append(
                PlayerArtistOut(
                    id=artist.id,
                    name=artist.name,
                    image_url=artist.image_url,
                    album_count=len(dl_albums),
                )
            )
        if len(albums_out) >= 20 and len(artists_out) >= 20:
            break
    db.commit()
    return PlayerSearchGroupedOut(
        top=top,
        songs=songs,
        albums=albums_out[:20],
        artists=artists_out[:20],
    )


@router.get("/stream/{track_id}")
def stream_track(track_id: int, request: Request, db: Session = Depends(get_db)):
    _current_player_user(request, db)
    track = db.scalar(
        select(Track).options(joinedload(Track.album)).where(Track.id == track_id)
    )
    if not track or not track.path:
        raise HTTPException(status_code=404, detail="Track not found")
    return _stream_file_response(track, request)


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
        pinned_playlist_ids=_parse_pinned_ids(getattr(user, "pinned_playlist_ids", "[]")),
        crossfade_enabled=bool(getattr(user, "crossfade_enabled", False)),
        show_recommended=bool(getattr(user, "show_recommended", True)),
        show_recently_added=bool(getattr(user, "show_recently_added", True)),
        default_shuffle=bool(getattr(user, "default_shuffle", False)),
        default_repeat=getattr(user, "default_repeat", None) or "off",
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
    if "pinned_playlist_ids" in data:
        ids = data.pop("pinned_playlist_ids")
        user.pinned_playlist_ids = json.dumps(list(ids or []))
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
            user.continue_album_id = track.album_id
            user.continue_track_id = track.id
            user.continue_position = float(payload.position or 0)
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
    db.commit()
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
    out = _builtin_meta(kind, name, loader())
    db.commit()
    return out


@router.get("/library/recommended", response_model=list[PlayerTrackOut])
def library_recommended(request: Request, db: Session = Depends(get_db)):
    user = _current_player_user(request, db)
    import random

    recent_events = db.scalars(
        select(PlayerPlayEvent)
        .where(PlayerPlayEvent.user_id == user.id)
        .order_by(PlayerPlayEvent.played_at.desc())
        .limit(50)
    ).all()
    recent_track_ids: set[int] = set()
    seed_artist_ids: set[int] = set()
    for ev in recent_events:
        recent_track_ids.add(ev.track_id)
        tr = db.get(Track, ev.track_id)
        if tr and tr.album:
            seed_artist_ids.add(tr.album.artist_id)

    fav_rows = db.scalars(
        select(PlayerFavorite)
        .options(joinedload(PlayerFavorite.track).joinedload(Track.album))
        .where(PlayerFavorite.user_id == user.id)
        .limit(100)
    ).unique().all()
    for row in fav_rows:
        if row.track and row.track.album:
            seed_artist_ids.add(row.track.album.artist_id)

    all_tracks = list(db.scalars(_downloaded_tracks_query()).unique().all())
    scored: list[tuple[int, Track]] = []
    for t in all_tracks:
        if t.id in recent_track_ids:
            continue
        score = 0
        if t.album and t.album.artist_id in seed_artist_ids:
            score += 10
        scored.append((score, t))
    scored.sort(key=lambda x: (-x[0], x[1].id))
    picks = [t for _, t in scored[:20]]
    if len(picks) < 20:
        pool = [t for t in all_tracks if t.id not in recent_track_ids and t not in picks]
        random.shuffle(pool)
        picks.extend(pool[: 20 - len(picks)])
    db.commit()
    return [_track_out(t) for t in picks[:20]]


@router.get("/library/albums", response_model=list[PlayerAlbumOut])
def library_albums(
    request: Request,
    sort: str = "recent",
    db: Session = Depends(get_db),
):
    _current_player_user(request, db)
    albums = db.scalars(
        select(Album)
        .options(joinedload(Album.tracks), joinedload(Album.artist))
        .where(Album.status == "downloaded")
    ).unique().all()
    playable = [a for a in albums if any(t.path for t in (a.tracks or []))]
    if sort == "name":
        playable.sort(key=lambda a: (a.title or "").lower())
    elif sort == "year":
        playable.sort(key=lambda a: (a.release_date or "", a.title or "").lower())
    else:
        playable = _sort_albums_newest(playable)
    return [_album_out(a) for a in playable]


@router.get("/library/songs", response_model=PlayerLibrarySongsPage)
def library_songs(
    request: Request,
    q: str = "",
    offset: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    _current_player_user(request, db)
    offset = max(0, offset)
    limit = min(max(1, limit), 200)
    query = (q or "").strip().lower()
    tracks = db.scalars(_downloaded_tracks_query().order_by(Track.title)).unique().all()
    if query:
        filtered = []
        for t in tracks:
            album = t.album
            artist = album.artist if album else None
            blob = " ".join(
                [t.title or "", album.title if album else "", artist.name if artist else ""]
            ).lower()
            if query in blob:
                filtered.append(t)
        tracks = filtered
    total = len(tracks)
    page = tracks[offset : offset + limit]
    db.commit()
    return PlayerLibrarySongsPage(
        items=[_track_out(t) for t in page],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/library/continue", response_model=PlayerContinueOut)
def library_continue(request: Request, db: Session = Depends(get_db)):
    user = _current_player_user(request, db)
    track: Track | None = None
    position = float(getattr(user, "continue_position", 0) or 0)
    source_label = ""

    if getattr(user, "continue_track_id", None):
        track = db.scalar(
            select(Track)
            .options(
                joinedload(Track.album).joinedload(Album.artist),
                joinedload(Track.album).joinedload(Album.tracks),
            )
            .where(Track.id == user.continue_track_id)
        )
        if not track or not track.path:
            track = None
        else:
            source_label = "Continue listening"

    if not track:
        ev = db.scalar(
            select(PlayerPlayEvent)
            .options(
                joinedload(PlayerPlayEvent.track)
                .joinedload(Track.album)
                .joinedload(Album.artist),
                joinedload(PlayerPlayEvent.track)
                .joinedload(Track.album)
                .joinedload(Album.tracks),
            )
            .where(PlayerPlayEvent.user_id == user.id)
            .order_by(PlayerPlayEvent.played_at.desc())
            .limit(1)
        )
        if ev and ev.track and ev.track.path:
            track = ev.track
            position = 0.0
            source_label = "Recently played"

    if not track:
        return PlayerContinueOut(source_label="")

    album = track.album
    db.commit()
    return PlayerContinueOut(
        album=_album_out(album, include_tracks=True) if album else None,
        track=_track_out(track),
        position=position,
        source_label=source_label,
    )


@router.delete("/library/history")
def clear_listen_history(request: Request, db: Session = Depends(get_db)):
    user = _current_player_user(request, db)
    rows = db.scalars(
        select(PlayerPlayEvent).where(PlayerPlayEvent.user_id == user.id)
    ).all()
    for row in rows:
        db.delete(row)
    user.continue_track_id = None
    user.continue_album_id = None
    user.continue_position = 0.0
    db.commit()
    return {"ok": True}


@router.get("/library/history", response_model=PlayerPlaylistOut)
def listen_history(request: Request, db: Session = Depends(get_db)):
    """Full listen history — always available (unlike the hideable Recently Played builtin)."""
    user = _current_player_user(request, db)
    tracks = _tracks_recently_played(db, user.id, limit=200)
    db.commit()
    return _builtin_meta("history", "Listening History", tracks)


_AVATAR_MAX_BYTES = 2 * 1024 * 1024
_AVATAR_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


def _avatar_dir() -> Path:
    d = app_config.data_dir / "player_avatars"
    d.mkdir(parents=True, exist_ok=True)
    return d


@router.post("/me/avatar")
async def upload_avatar(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    user = _current_player_user(request, db)
    content_type = (file.content_type or "").split(";")[0].strip().lower()
    ext = _AVATAR_TYPES.get(content_type)
    if not ext:
        raise HTTPException(status_code=400, detail="Image must be JPEG, PNG, or WebP")
    data = await file.read()
    if len(data) > _AVATAR_MAX_BYTES:
        raise HTTPException(status_code=400, detail="Avatar must be at most 2MB")
    dest = _avatar_dir() / f"{user.id}.{ext}"
    old_path = getattr(user, "avatar_path", None)
    dest.write_bytes(data)
    user.avatar_path = str(dest)
    db.commit()
    if old_path and old_path != str(dest):
        try:
            Path(old_path).unlink(missing_ok=True)
        except OSError:
            pass
    return {"ok": True, "avatar_url": _avatar_url(user)}


@router.delete("/me/avatar")
def delete_avatar(request: Request, db: Session = Depends(get_db)):
    user = _current_player_user(request, db)
    old_path = getattr(user, "avatar_path", None)
    user.avatar_path = None
    db.commit()
    if old_path:
        try:
            Path(old_path).unlink(missing_ok=True)
        except OSError:
            pass
    return {"ok": True}


@router.get("/avatars/{user_id}")
def get_avatar(user_id: int, request: Request, db: Session = Depends(get_db)):
    _require_player_or_admin(request, db)
    user = db.get(PlayerUser, user_id)
    if not user or not getattr(user, "avatar_path", None):
        raise HTTPException(status_code=404, detail="Avatar not found")
    path = Path(user.avatar_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Avatar not found")
    media_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type)


@router.post("/shares", response_model=PlayerShareOut)
def create_share(
    payload: PlayerShareCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    user = _current_player_user(request, db)
    if not _sharing_enabled(db):
        raise HTTPException(status_code=403, detail="Sharing is disabled")
    track = db.scalar(
        select(Track)
        .options(joinedload(Track.album).joinedload(Album.artist))
        .where(Track.id == payload.track_id)
    )
    if not track or not track.path:
        raise HTTPException(status_code=404, detail="Track not found")
    now = datetime.now(timezone.utc)
    token = secrets.token_urlsafe(32)
    link = PlayerShareLink(
        token=token,
        track_id=track.id,
        created_by_user_id=user.id,
        created_at=now,
        expires_at=now + timedelta(days=30),
        revoked=False,
        play_count=0,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    link.track = track
    return _share_out(link, request)


@router.get("/shares", response_model=list[PlayerShareOut])
def list_shares(request: Request, db: Session = Depends(get_db)):
    user = _current_player_user(request, db)
    rows = db.scalars(
        select(PlayerShareLink)
        .options(
            joinedload(PlayerShareLink.track)
            .joinedload(Track.album)
            .joinedload(Album.artist)
        )
        .where(PlayerShareLink.created_by_user_id == user.id)
        .order_by(PlayerShareLink.created_at.desc())
    ).unique().all()
    return [_share_out(r, request) for r in rows]


@router.delete("/shares/{token}")
def revoke_share(token: str, request: Request, db: Session = Depends(get_db)):
    user = _current_player_user(request, db)
    link = db.scalar(
        select(PlayerShareLink).where(
            PlayerShareLink.token == token,
            PlayerShareLink.created_by_user_id == user.id,
        )
    )
    if not link:
        raise HTTPException(status_code=404, detail="Share not found")
    link.revoked = True
    db.commit()
    return {"ok": True}


@router.get("/share/{token}", response_model=PlayerSharePublicOut)
def share_public_meta(token: str, db: Session = Depends(get_db)):
    if not player_auth.player_enabled(db):
        raise HTTPException(status_code=404, detail="Player is disabled")
    link = db.scalar(
        select(PlayerShareLink)
        .options(
            joinedload(PlayerShareLink.track)
            .joinedload(Track.album)
            .joinedload(Album.artist),
            joinedload(PlayerShareLink.created_by),
        )
        .where(PlayerShareLink.token == token)
    )
    link = _valid_share(link)
    track = link.track
    if not track or not track.path:
        raise HTTPException(status_code=404, detail="Track not found")
    album = track.album
    artist = album.artist if album else None
    creator = link.created_by
    has_avatar = bool(creator and getattr(creator, "avatar_path", None))
    return PlayerSharePublicOut(
        title=track.title,
        artist=artist.name if artist else "",
        album=album.title if album else "",
        cover_url=album.cover_url if album else None,
        duration=_ensure_track_duration(track),
        shared_by_display_name=(creator.display_name or creator.username) if creator else "",
        shared_by_avatar_url=(f"/api/player/share/{token}/avatar" if has_avatar else None),
    )


@router.get("/share/{token}/stream")
def share_public_stream(token: str, request: Request, db: Session = Depends(get_db)):
    if not player_auth.player_enabled(db):
        raise HTTPException(status_code=404, detail="Player is disabled")
    link = db.scalar(
        select(PlayerShareLink)
        .options(joinedload(PlayerShareLink.track).joinedload(Track.album))
        .where(PlayerShareLink.token == token)
    )
    link = _valid_share(link)
    track = link.track
    if not track or not track.path:
        raise HTTPException(status_code=404, detail="Track not found")
    link.play_count = int(link.play_count or 0) + 1
    db.commit()
    return _stream_file_response(track, request)


@router.get("/share/{token}/avatar")
def share_public_avatar(token: str, db: Session = Depends(get_db)):
    """Avatar for share page guests — gated by a valid share token only."""
    if not player_auth.player_enabled(db):
        raise HTTPException(status_code=404, detail="Player is disabled")
    link = db.scalar(
        select(PlayerShareLink)
        .options(joinedload(PlayerShareLink.created_by))
        .where(PlayerShareLink.token == token)
    )
    link = _valid_share(link)
    creator = link.created_by
    if not creator or not getattr(creator, "avatar_path", None):
        raise HTTPException(status_code=404, detail="Avatar not found")
    path = Path(creator.avatar_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Avatar not found")
    media_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type)


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
