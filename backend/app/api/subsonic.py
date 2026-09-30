"""Subsonic / OpenSubsonic compatible API so third-party clients (Symfonium,
DSub, Feishin, Substreamer...) can play the library.

Auth uses a per-user Subsonic secret (Player settings -> Subsonic), never the
login password: the token scheme (md5(secret + salt)) needs the plain secret on
the server, so it must be a separate, revocable credential.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import mimetypes
import os
import secrets
from datetime import datetime, timezone
from xml.sax.saxutils import escape, quoteattr

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.api.player import _current_player_user, _downloaded_tracks_query, _stream_file_response
from app.core.database import get_db
from app.models import (
    Album,
    Artist,
    PlayerFavorite,
    PlayerPlayEvent,
    PlayerPlaylist,
    PlayerPlaylistMember,
    PlayerPlaylistTrack,
    PlayerUser,
    Track,
)
from app.services import player_auth
from app.services.smart_playlists import evaluate_smart_playlist, parse_criteria

API_VERSION = "1.16.1"
SERVER_VERSION = "1.22"

router = APIRouter(tags=["subsonic"])
settings_router = APIRouter(prefix="/player/subsonic", tags=["subsonic"])


class SubsonicError(Exception):
    def __init__(self, code: int, message: str):
        self.code, self.message = code, message


# ---------- response rendering ----------


def _xml_node(name: str, value) -> str:
    if isinstance(value, dict):
        attrs, children = [], []
        for k, v in value.items():
            if isinstance(v, (dict, list)):
                children.append((k, v))
            elif v is not None:
                attrs.append(f" {k}={quoteattr(_scalar(v))}")
        inner = "".join(_xml_node(k, v) for k, v in children)
        return f"<{name}{''.join(attrs)}>{inner}</{name}>" if inner else f"<{name}{''.join(attrs)}/>"
    if isinstance(value, list):
        return "".join(_xml_node(name, item) for item in value)
    return f"<{name}>{escape(_scalar(value))}</{name}>"


def _scalar(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def _render(request: Request, payload: dict, *, error: SubsonicError | None = None) -> Response:
    body: dict = {
        "status": "failed" if error else "ok",
        "version": API_VERSION,
        "type": "musicarr",
        "serverVersion": SERVER_VERSION,
        "openSubsonic": True,
    }
    if error:
        body["error"] = {"code": error.code, "message": error.message}
    else:
        body.update(payload)
    fmt = (request.query_params.get("f") or "xml").lower()
    if fmt in ("json", "jsonp"):
        return JSONResponse({"subsonic-response": body})
    xml = _xml_node("subsonic-response", {"xmlns": "http://subsonic.org/restapi", **body})
    return Response('<?xml version="1.0" encoding="UTF-8"?>\n' + xml, media_type="text/xml")


# ---------- auth & params ----------


async def _params(request: Request) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for k, v in request.query_params.multi_items():
        out.setdefault(k, []).append(v)
    if request.method == "POST":
        try:
            form = await request.form()
            for k, v in form.multi_items():
                out.setdefault(k, []).append(str(v))
        except Exception:  # noqa: BLE001
            pass
    return out


def _first(p: dict[str, list[str]], key: str, default: str | None = None) -> str | None:
    vals = p.get(key)
    return vals[0] if vals else default


def _int(p, key: str, default: int) -> int:
    try:
        return int(_first(p, key, str(default)) or default)
    except ValueError:
        return default


def _authenticate(db: Session, p: dict[str, list[str]]) -> PlayerUser:
    username = (_first(p, "u") or "").strip()
    if not username:
        raise SubsonicError(10, "Required parameter is missing: u")
    if not player_auth.player_enabled(db):
        raise SubsonicError(50, "Player is disabled")
    user = db.scalar(select(PlayerUser).where(func.lower(PlayerUser.username) == username.lower()))
    secret = (user.subsonic_secret or "") if user and user.is_active else ""
    token, salt, pw = _first(p, "t"), _first(p, "s"), _first(p, "p")
    ok = False
    if secret:
        if token and salt:
            ok = hmac.compare_digest(hashlib.md5((secret + salt).encode()).hexdigest(), token.lower())
        elif pw:
            if pw.startswith("enc:"):
                try:
                    pw = bytes.fromhex(pw[4:]).decode()
                except ValueError:
                    pw = ""
            ok = hmac.compare_digest(pw, secret)
    if not ok:
        raise SubsonicError(40, "Wrong username or password")
    return user


# ---------- mappers ----------


def _iso(dt: datetime | None) -> str:
    dt = dt or datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _year(album: Album | None) -> int | None:
    rd = (album.release_date or "")[:4] if album else ""
    return int(rd) if rd.isdigit() else None


def _song(t: Track, starred: set[int]) -> dict:
    album, artist = t.album, (t.album.artist if t.album else None)
    suffix = os.path.splitext(t.path or "")[1].lstrip(".").lower()
    try:
        size = os.path.getsize(t.path) if t.path else 0
    except OSError:
        size = 0
    out = {
        "id": f"tr-{t.id}",
        "parent": f"al-{t.album_id}",
        "isDir": False,
        "title": t.title,
        "album": album.title if album else "",
        "artist": artist.name if artist else "",
        "track": t.track_no or None,
        "discNumber": t.disc_no or 1,
        "year": _year(album),
        "genre": t.genre or None,
        "coverArt": f"al-{t.album_id}",
        "size": size,
        "contentType": mimetypes.guess_type(t.path or "")[0] or "audio/mpeg",
        "suffix": suffix,
        "duration": t.duration or 0,
        "path": f"{artist.name if artist else 'Unknown'}/{album.title if album else 'Unknown'}/{os.path.basename(t.path or '')}",
        "albumId": f"al-{t.album_id}",
        "artistId": f"ar-{artist.id}" if artist else None,
        "type": "music",
        "isVideo": False,
    }
    if t.id in starred:
        out["starred"] = _iso(None)
    return out


def _album_entry(a: Album, song_count: int, duration: int) -> dict:
    return {
        "id": f"al-{a.id}",
        "name": a.title,
        "title": a.title,
        "album": a.title,
        "artist": a.artist.name if a.artist else "",
        "artistId": f"ar-{a.artist_id}",
        "parent": f"ar-{a.artist_id}",
        "isDir": True,
        "coverArt": f"al-{a.id}",
        "songCount": song_count,
        "duration": duration,
        "year": _year(a),
        "created": _iso(a.added_at if hasattr(a, "added_at") else None),
    }


def _starred_ids(db: Session, user: PlayerUser) -> set[int]:
    return set(db.scalars(select(PlayerFavorite.track_id).where(PlayerFavorite.user_id == user.id)))


def _album_stats(db: Session, album_ids: list[int]) -> dict[int, tuple[int, int]]:
    if not album_ids:
        return {}
    rows = db.execute(
        select(Track.album_id, func.count(Track.id), func.coalesce(func.sum(Track.duration), 0))
        .where(Track.album_id.in_(album_ids), Track.path.is_not(None), Track.path != "")
        .group_by(Track.album_id)
    ).all()
    return {r[0]: (r[1], int(r[2])) for r in rows}


def _albums_with_music(db: Session):
    return (
        select(Album)
        .options(joinedload(Album.artist))
        .where(
            Album.id.in_(
                select(Track.album_id).where(Track.path.is_not(None), Track.path != "")
            )
        )
    )


def _albums_out(db: Session, albums: list[Album]) -> list[dict]:
    stats = _album_stats(db, [a.id for a in albums])
    return [_album_entry(a, *stats.get(a.id, (0, 0))) for a in albums]


def _num(raw: str | None, prefix: str) -> int:
    v = (raw or "").strip()
    if v.startswith(prefix):
        v = v[len(prefix):]
    if not v.isdigit():
        raise SubsonicError(70, "Requested data was not found")
    return int(v)


def _playlist_tracks(db: Session, pl: PlayerPlaylist) -> list[Track]:
    if parse_criteria(pl):
        return [t for t in evaluate_smart_playlist(db, pl) if t.path]
    rows = db.scalars(
        select(PlayerPlaylistTrack)
        .options(joinedload(PlayerPlaylistTrack.track).joinedload(Track.album).joinedload(Album.artist))
        .where(PlayerPlaylistTrack.playlist_id == pl.id)
        .order_by(PlayerPlaylistTrack.position)
    ).unique().all()
    return [r.track for r in rows if r.track and r.track.path]


def _playlist_entry(db: Session, pl: PlayerPlaylist, owner: str, tracks: list[Track]) -> dict:
    return {
        "id": f"pl-{pl.id}",
        "name": pl.name,
        "owner": owner,
        "public": False,
        "songCount": len(tracks),
        "duration": sum(t.duration or 0 for t in tracks),
        "created": _iso(pl.created_at),
        "changed": _iso(pl.updated_at),
        "coverArt": f"al-{tracks[0].album_id}" if tracks else None,
    }


def _accessible_playlists(db: Session, user: PlayerUser) -> list[PlayerPlaylist]:
    return list(
        db.scalars(
            select(PlayerPlaylist)
            .options(joinedload(PlayerPlaylist.user))
            .where(
                (PlayerPlaylist.user_id == user.id)
                | PlayerPlaylist.id.in_(
                    select(PlayerPlaylistMember.playlist_id).where(
                        PlayerPlaylistMember.user_id == user.id
                    )
                )
            )
            .order_by(PlayerPlaylist.name)
        ).unique()
    )


def _get_playlist(db: Session, user: PlayerUser, raw_id: str | None) -> PlayerPlaylist:
    pid = _num(raw_id, "pl-")
    for pl in _accessible_playlists(db, user):
        if pl.id == pid:
            return pl
    raise SubsonicError(70, "Playlist not found")


# ---------- handlers ----------
# Each returns the payload dict merged into <subsonic-response>, or a Response.


def h_ping(db, user, p, request):
    return {}


def h_get_license(db, user, p, request):
    return {"license": {"valid": True, "email": "", "licenseExpires": "2099-01-01T00:00:00.000Z"}}


def h_music_folders(db, user, p, request):
    return {"musicFolders": {"musicFolder": [{"id": 1, "name": "Music"}]}}


def _artist_rows(db: Session):
    rows = db.execute(
        select(Artist, func.count(func.distinct(Album.id)))
        .join(Album, Album.artist_id == Artist.id)
        .join(Track, Track.album_id == Album.id)
        .where(Track.path.is_not(None), Track.path != "")
        .group_by(Artist.id)
        .order_by(func.lower(Artist.name))
    ).all()
    return rows


def _artist_index(db: Session, key: str) -> dict:
    groups: dict[str, list[dict]] = {}
    for a, n in _artist_rows(db):
        letter = (a.name[:1] or "#").upper()
        letter = letter if letter.isalpha() else "#"
        groups.setdefault(letter, []).append(
            {"id": f"ar-{a.id}", "name": a.name, "albumCount": n, "artistImageUrl": a.image_url}
        )
    body = {"ignoredArticles": "", "index": [{"name": k, "artist": v} for k, v in sorted(groups.items())]}
    if key == "indexes":
        body["lastModified"] = 0
    return {key: body}


def h_get_artists(db, user, p, request):
    return _artist_index(db, "artists")


def h_get_indexes(db, user, p, request):
    return _artist_index(db, "indexes")


def h_get_artist(db, user, p, request):
    aid = _num(_first(p, "id"), "ar-")
    artist = db.get(Artist, aid)
    if not artist:
        raise SubsonicError(70, "Artist not found")
    albums = list(
        db.scalars(_albums_with_music(db).where(Album.artist_id == aid).order_by(Album.release_date.desc())).unique()
    )
    entries = _albums_out(db, albums)
    return {
        "artist": {
            "id": f"ar-{artist.id}",
            "name": artist.name,
            "albumCount": len(entries),
            "artistImageUrl": artist.image_url,
            "album": entries,
        }
    }


def h_get_album(db, user, p, request):
    aid = _num(_first(p, "id"), "al-")
    album = db.scalar(select(Album).options(joinedload(Album.artist)).where(Album.id == aid))
    if not album:
        raise SubsonicError(70, "Album not found")
    tracks = list(
        db.scalars(
            _downloaded_tracks_query()
            .where(Track.album_id == aid)
            .order_by(Track.disc_no, Track.track_no)
        ).unique()
    )
    starred = _starred_ids(db, user)
    entry = _album_entry(album, len(tracks), sum(t.duration or 0 for t in tracks))
    entry["song"] = [_song(t, starred) for t in tracks]
    return {"album": entry}


def h_get_song(db, user, p, request):
    t = db.scalar(_downloaded_tracks_query().where(Track.id == _num(_first(p, "id"), "tr-")))
    if not t:
        raise SubsonicError(70, "Song not found")
    return {"song": _song(t, _starred_ids(db, user))}


def h_album_list2(db, user, p, request):
    kind = _first(p, "type", "alphabeticalByName")
    size = max(1, min(_int(p, "size", 10), 500))
    offset = max(0, _int(p, "offset", 0))
    stmt = _albums_with_music(db)
    if kind == "alphabeticalByArtist":
        stmt = stmt.join(Artist, Artist.id == Album.artist_id).order_by(func.lower(Artist.name), Album.title)
    elif kind == "newest":
        stmt = stmt.order_by(Album.id.desc())
    elif kind == "random":
        stmt = stmt.order_by(func.random())
    elif kind == "byYear":
        lo, hi = _int(p, "fromYear", 0), _int(p, "toYear", 9999)
        stmt = stmt.where(func.substr(Album.release_date, 1, 4).between(str(lo), str(hi))).order_by(
            Album.release_date.desc() if lo > hi else Album.release_date
        )
    elif kind == "byGenre":
        g = (_first(p, "genre") or "").lower()
        stmt = stmt.where(
            Album.id.in_(select(Track.album_id).where(func.lower(Track.genre) == g))
        ).order_by(Album.title)
    elif kind in ("frequent", "recent"):
        col = func.count(PlayerPlayEvent.id) if kind == "frequent" else func.max(PlayerPlayEvent.played_at)
        ids = [
            r[0]
            for r in db.execute(
                select(Track.album_id, col.label("c"))
                .join(PlayerPlayEvent, PlayerPlayEvent.track_id == Track.id)
                .where(PlayerPlayEvent.user_id == user.id)
                .group_by(Track.album_id)
                .order_by(col.desc())
                .limit(size).offset(offset)
            )
        ]
        albums = {a.id: a for a in db.scalars(_albums_with_music(db).where(Album.id.in_(ids))).unique()}
        return {"albumList2": {"album": _albums_out(db, [albums[i] for i in ids if i in albums])}}
    elif kind == "starred":
        stmt = stmt.where(
            Album.id.in_(
                select(Track.album_id)
                .join(PlayerFavorite, PlayerFavorite.track_id == Track.id)
                .where(PlayerFavorite.user_id == user.id)
            )
        ).order_by(Album.title)
    else:
        stmt = stmt.order_by(func.lower(Album.title))
    albums = list(db.scalars(stmt.limit(size).offset(offset)).unique())
    return {"albumList2": {"album": _albums_out(db, albums)}}


def h_search3(db, user, p, request):
    q = (_first(p, "query") or "").strip().strip('"').lower()
    ac, alc, sc = _int(p, "artistCount", 20), _int(p, "albumCount", 20), _int(p, "songCount", 20)
    aoff, aloff, soff = _int(p, "artistOffset", 0), _int(p, "albumOffset", 0), _int(p, "songOffset", 0)
    like = f"%{q}%"
    artists = [
        {"id": f"ar-{a.id}", "name": a.name, "albumCount": n, "artistImageUrl": a.image_url}
        for a, n in _artist_rows(db)
        if not q or q in a.name.lower()
    ][aoff : aoff + ac]
    albums = list(
        db.scalars(
            _albums_with_music(db)
            .join(Artist, Artist.id == Album.artist_id)
            .where(func.lower(Album.title).like(like) | func.lower(Artist.name).like(like))
            .order_by(func.lower(Album.title))
            .limit(alc).offset(aloff)
        ).unique()
    )
    songs = list(
        db.scalars(
            _downloaded_tracks_query()
            .join(Album, Album.id == Track.album_id)
            .join(Artist, Artist.id == Album.artist_id)
            .where(func.lower(Track.title).like(like) | func.lower(Artist.name).like(like))
            .order_by(func.lower(Track.title))
            .limit(sc).offset(soff)
        ).unique()
    )
    starred = _starred_ids(db, user)
    return {
        "searchResult3": {
            "artist": artists,
            "album": _albums_out(db, albums),
            "song": [_song(t, starred) for t in songs],
        }
    }


def h_random_songs(db, user, p, request):
    size = max(1, min(_int(p, "size", 10), 500))
    stmt = _downloaded_tracks_query().order_by(func.random()).limit(size)
    g = _first(p, "genre")
    if g:
        stmt = stmt.where(func.lower(Track.genre) == g.lower())
    starred = _starred_ids(db, user)
    return {"randomSongs": {"song": [_song(t, starred) for t in db.scalars(stmt).unique()]}}


def h_genres(db, user, p, request):
    rows = db.execute(
        select(Track.genre, func.count(Track.id), func.count(func.distinct(Track.album_id)))
        .where(Track.path.is_not(None), Track.path != "", Track.genre != "")
        .group_by(Track.genre)
        .order_by(Track.genre)
    ).all()
    return {"genres": {"genre": [{"value": g, "songCount": s, "albumCount": a} for g, s, a in rows]}}


def h_starred2(db, user, p, request):
    tracks = list(
        db.scalars(
            _downloaded_tracks_query()
            .join(PlayerFavorite, PlayerFavorite.track_id == Track.id)
            .where(PlayerFavorite.user_id == user.id)
        ).unique()
    )
    return {"starred2": {"song": [_song(t, {t.id for t in tracks}) for t in tracks]}}


def _track_ids(p, key="id") -> list[int]:
    out = []
    for raw in p.get(key, []):
        if raw.startswith("tr-") and raw[3:].isdigit():
            out.append(int(raw[3:]))
    return out


def h_star(db, user, p, request):
    have = _starred_ids(db, user)
    for tid in _track_ids(p):
        if tid not in have and db.get(Track, tid):
            db.add(PlayerFavorite(user_id=user.id, track_id=tid))
    db.commit()
    return {}


def h_unstar(db, user, p, request):
    for tid in _track_ids(p):
        db.query(PlayerFavorite).filter(
            PlayerFavorite.user_id == user.id, PlayerFavorite.track_id == tid
        ).delete()
    db.commit()
    return {}


def h_scrobble(db, user, p, request):
    if (_first(p, "submission", "true") or "true").lower() != "false":
        for tid in _track_ids(p):
            if db.get(Track, tid):
                db.add(PlayerPlayEvent(user_id=user.id, track_id=tid))
        db.commit()
    return {}


def h_playlists(db, user, p, request):
    out = []
    for pl in _accessible_playlists(db, user):
        out.append(_playlist_entry(db, pl, pl.user.username if pl.user else "", _playlist_tracks(db, pl)))
    return {"playlists": {"playlist": out}}


def h_playlist(db, user, p, request):
    pl = _get_playlist(db, user, _first(p, "id"))
    tracks = _playlist_tracks(db, pl)
    starred = _starred_ids(db, user)
    entry = _playlist_entry(db, pl, pl.user.username if pl.user else "", tracks)
    entry["entry"] = [_song(t, starred) for t in tracks]
    return {"playlist": entry}


def _add_tracks(db: Session, pl: PlayerPlaylist, user: PlayerUser, ids: list[int]) -> None:
    existing = {r.track_id for r in db.scalars(select(PlayerPlaylistTrack).where(PlayerPlaylistTrack.playlist_id == pl.id))}
    pos = (db.scalar(select(func.max(PlayerPlaylistTrack.position)).where(PlayerPlaylistTrack.playlist_id == pl.id)) or -1) + 1
    for tid in ids:
        if tid in existing or not db.get(Track, tid):
            continue
        db.add(PlayerPlaylistTrack(playlist_id=pl.id, track_id=tid, position=pos, added_by_user_id=user.id))
        existing.add(tid)
        pos += 1
    pl.updated_at = datetime.now(timezone.utc)


def h_create_playlist(db, user, p, request):
    pid = _first(p, "playlistId")
    if pid:
        pl = _get_playlist(db, user, pid)
    else:
        name = (_first(p, "name") or "").strip()
        if not name:
            raise SubsonicError(10, "Required parameter is missing: name")
        now = datetime.now(timezone.utc)
        pl = PlayerPlaylist(user_id=user.id, name=name, created_at=now, updated_at=now)
        db.add(pl)
        db.flush()
    _add_tracks(db, pl, user, _track_ids(p, "songId"))
    db.commit()
    return h_playlist(db, user, {"id": [f"pl-{pl.id}"]}, request)


def h_update_playlist(db, user, p, request):
    pl = _get_playlist(db, user, _first(p, "playlistId"))
    if parse_criteria(pl):
        raise SubsonicError(50, "Smart playlists are computed from rules")
    name = _first(p, "name")
    if name and pl.user_id == user.id:
        pl.name = name.strip()
    tracks = _playlist_tracks(db, pl)
    drop = {tracks[i].id for i in (int(x) for x in p.get("songIndexToRemove", []) if x.isdigit()) if 0 <= i < len(tracks)}
    if drop:
        db.query(PlayerPlaylistTrack).filter(
            PlayerPlaylistTrack.playlist_id == pl.id, PlayerPlaylistTrack.track_id.in_(drop)
        ).delete(synchronize_session=False)
    _add_tracks(db, pl, user, _track_ids(p, "songIdToAdd"))
    pl.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {}


def h_delete_playlist(db, user, p, request):
    pl = _get_playlist(db, user, _first(p, "id"))
    if pl.user_id != user.id:
        raise SubsonicError(50, "Only the owner can delete a playlist")
    db.delete(pl)
    db.commit()
    return {}


def h_user(db, user, p, request):
    return {
        "user": {
            "username": user.username,
            "email": "",
            "scrobblingEnabled": True,
            "adminRole": False,
            "settingsRole": False,
            "downloadRole": True,
            "uploadRole": False,
            "playlistRole": True,
            "coverArtRole": False,
            "commentRole": False,
            "podcastRole": False,
            "streamRole": True,
            "jukeboxRole": False,
            "shareRole": False,
            "folder": [1],
        }
    }


def h_extensions(db, user, p, request):
    return {"openSubsonicExtensions": []}


def h_stream(db, user, p, request):
    t = db.scalar(_downloaded_tracks_query().where(Track.id == _num(_first(p, "id"), "tr-")))
    if not t:
        raise SubsonicError(70, "Song not found")
    return _stream_file_response(t, request)


def h_cover_art(db, user, p, request):
    raw = _first(p, "id") or ""
    album_id = None
    if raw.startswith("al-") and raw[3:].isdigit():
        album_id = int(raw[3:])
    elif raw.startswith("tr-") and raw[3:].isdigit():
        t = db.get(Track, int(raw[3:]))
        album_id = t.album_id if t else None
    elif raw.startswith("ar-") and raw[3:].isdigit():
        a = db.get(Artist, int(raw[3:]))
        if a and a.image_url:
            return RedirectResponse(a.image_url)
    album = db.get(Album, album_id) if album_id else None
    if not album or not album.cover_url:
        raise SubsonicError(70, "Cover art not found")
    url = album.cover_url
    if _int(p, "size", 0) > 250 and url.endswith("-250"):
        url = url[:-4] + "-500"
    return RedirectResponse(url)


HANDLERS = {
    "ping": h_ping,
    "getLicense": h_get_license,
    "getMusicFolders": h_music_folders,
    "getArtists": h_get_artists,
    "getIndexes": h_get_indexes,
    "getArtist": h_get_artist,
    "getAlbum": h_get_album,
    "getSong": h_get_song,
    "getAlbumList2": h_album_list2,
    "getAlbumList": h_album_list2,
    "search3": h_search3,
    "search2": h_search3,
    "getRandomSongs": h_random_songs,
    "getGenres": h_genres,
    "getStarred2": h_starred2,
    "getStarred": h_starred2,
    "star": h_star,
    "unstar": h_unstar,
    "scrobble": h_scrobble,
    "getPlaylists": h_playlists,
    "getPlaylist": h_playlist,
    "createPlaylist": h_create_playlist,
    "updatePlaylist": h_update_playlist,
    "deletePlaylist": h_delete_playlist,
    "getUser": h_user,
    "getOpenSubsonicExtensions": h_extensions,
    "stream": h_stream,
    "download": h_stream,
    "getCoverArt": h_cover_art,
}


@router.api_route("/rest/{method}", methods=["GET", "POST"])
async def dispatch(method: str, request: Request, db: Session = Depends(get_db)):
    name = method[:-5] if method.endswith(".view") else method
    p = await _params(request)
    try:
        user = _authenticate(db, p)
        handler = HANDLERS.get(name)
        if not handler:
            raise SubsonicError(70, f"Unsupported method: {name}")
        result = handler(db, user, p, request)
    except SubsonicError as e:
        return _render(request, {}, error=e)
    except HTTPException as e:
        return _render(request, {}, error=SubsonicError(70 if e.status_code == 404 else 0, str(e.detail)))
    except Exception:  # noqa: BLE001
        # Subsonic clients can't parse an HTML 500 page; give them a protocol error.
        logging.getLogger(__name__).exception("Subsonic %s failed", name)
        db.rollback()
        return _render(request, {}, error=SubsonicError(0, "Internal server error"))
    if isinstance(result, Response):
        return result
    return _render(request, result)


# ---------- per-user secret management (Player settings) ----------


@settings_router.get("")
def get_subsonic(request: Request, db: Session = Depends(get_db)):
    user = _current_player_user(request, db)
    return {"username": user.username, "secret": user.subsonic_secret}


@settings_router.post("/regenerate")
def regenerate_subsonic(request: Request, db: Session = Depends(get_db)):
    user = _current_player_user(request, db)
    user.subsonic_secret = secrets.token_urlsafe(18)
    db.commit()
    return {"username": user.username, "secret": user.subsonic_secret}


@settings_router.delete("")
def revoke_subsonic(request: Request, db: Session = Depends(get_db)):
    user = _current_player_user(request, db)
    user.subsonic_secret = None
    db.commit()
    return {"ok": True}
