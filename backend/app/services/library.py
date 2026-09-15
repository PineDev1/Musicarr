from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from mutagen import File as MutagenFile
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import Album, Artist, Track
from app.services.history import add_history
from app.services.naming import (
    artist_folder_name,
    build_album_folder,
    build_track_filename,
    year_from_release,
)
from app.services.settings_service import ensure_settings, library_root


AUDIO_EXTS = {".flac", ".mp3", ".m4a", ".ogg", ".opus", ".wav", ".aac", ".aiff", ".aif"}


def _norm(s: str | None) -> str:
    t = (s or "").lower().strip()
    t = re.sub(r"\([^)]*\)", "", t)
    t = re.sub(r"\[[^\]]*\]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _slug_id(text: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", _norm(text)).strip("-") or "unknown"
    return base[:60]


def _read_tags(path: Path) -> dict:
    meta = {
        "title": None,
        "artist": None,
        "album_artist": None,
        "album": None,
        "track": None,
        "disc": None,
        "isrc": None,
        "date": None,
    }
    try:
        audio = MutagenFile(path, easy=True)
        if not audio or not audio.tags:
            return meta
        tags = audio.tags

        def first(key: str):
            val = tags.get(key)
            if isinstance(val, list) and val:
                return str(val[0])
            if val:
                return str(val)
            return None

        meta["title"] = first("title")
        meta["artist"] = first("artist")
        meta["album_artist"] = first("albumartist") or first("album artist")
        meta["album"] = first("album")
        meta["isrc"] = first("isrc")
        meta["date"] = first("date") or first("year")
        track = first("tracknumber")
        if track:
            meta["track"] = track.split("/")[0]
        disc = first("discnumber")
        if disc:
            meta["disc"] = disc.split("/")[0]
    except Exception:  # noqa: BLE001
        pass
    return meta


def _guess_from_path(path: Path, root: Path) -> dict:
    """Fallback Artist/Album/Title from folder layout: Artist/Album/Track.ext"""
    try:
        rel = path.relative_to(root)
    except ValueError:
        rel = path
    parts = list(rel.parts)
    artist = parts[0] if len(parts) >= 3 else None
    album = parts[1] if len(parts) >= 3 else (parts[0] if len(parts) == 2 else None)
    title = path.stem
    # Strip leading track numbers: "01 - Song" / "01. Song"
    title = re.sub(r"^\d+[\s.\-_]+", "", title).strip() or path.stem
    return {"artist": artist, "album": album, "title": title}


def _collect_files(root: Path) -> list[dict]:
    out: list[dict] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in AUDIO_EXTS:
            continue
        tags = _read_tags(path)
        guess = _guess_from_path(path, root)
        artist = tags.get("album_artist") or tags.get("artist") or guess.get("artist") or "Unknown Artist"
        album = tags.get("album") or guess.get("album") or "Unknown Album"
        title = tags.get("title") or guess.get("title") or path.stem
        try:
            track_no = int(tags["track"]) if tags.get("track") else 0
        except ValueError:
            track_no = 0
        try:
            disc_no = int(tags["disc"]) if tags.get("disc") else 1
        except ValueError:
            disc_no = 1
        year = None
        if tags.get("date"):
            m = re.search(r"(\d{4})", str(tags["date"]))
            year = m.group(1) if m else None
        out.append(
            {
                "path": path,
                "artist": artist.strip(),
                "album": album.strip(),
                "title": title.strip(),
                "track_no": track_no,
                "disc_no": disc_no or 1,
                "isrc": tags.get("isrc"),
                "year": year,
            }
        )
    return out


def _find_artist_by_name(db: Session, name: str) -> Artist | None:
    """Exact normalized name match only. Ambiguous same-name rows return None."""
    key = _norm(name)
    if not key:
        return None
    artists = db.scalars(select(Artist)).all()
    exact = [a for a in artists if _norm(a.name) == key]
    if len(exact) == 1:
        return exact[0]
    return None


def _ensure_local_artist(db: Session, name: str, *, uniq_key: str | None = None) -> Artist:
    slug = _slug_id(name)
    if uniq_key:
        import hashlib

        digest = hashlib.sha1(uniq_key.encode("utf-8")).hexdigest()[:8]
        slug = f"{slug}-{digest}"[:60]
    existing = db.scalar(
        select(Artist).where(
            Artist.provider == "local",
            Artist.provider_id == slug,
        )
    )
    if existing:
        return existing
    # Reuse only when the name uniquely identifies one row
    by_name = _find_artist_by_name(db, name)
    if by_name and not uniq_key:
        return by_name
    from app.services.artists import _legacy_id

    artist = Artist(
        provider="local",
        provider_id=slug,
        deezer_id=_legacy_id("local", slug),
        name=name,
        image_url=None,
        monitored=True,
    )
    db.add(artist)
    db.commit()
    db.refresh(artist)
    add_history(db, "artist_imported", f"Imported local artist {name}")
    return artist


def _try_link_provider_artist(db: Session, name: str) -> Artist | None:
    """Search active provider and add artist without queuing downloads."""
    settings = ensure_settings(db)
    active = (settings.active_provider or "deezer").lower()
    try:
        from app.services.providers import get_provider
        from app.services.artists import add_artist
        from app.services.download_queue import pick_unique_artist_search_hit

        provider = get_provider(db, active)
        ok, _ = provider.validate_session()
        if not ok:
            return None
        hits = provider.search_artists(name, limit=8)
        if not hits:
            return None
        match = pick_unique_artist_search_hit(name, hits)
        if match is None:
            return None
        return add_artist(
            db,
            match.provider_id,
            monitored=True,
            download_missing=False,
            provider_name=active,
        )
    except Exception:  # noqa: BLE001
        return None


def _find_or_create_album(
    db: Session,
    artist: Artist,
    album_title: str,
    *,
    year: str | None,
    track_count: int,
) -> Album:
    albums = list(artist.albums or [])
    # Only scan explicitly linked artists (link_group_id), never name twins
    group_id = (getattr(artist, "link_group_id", None) or "").strip()
    if group_id:
        linked = db.scalars(
            select(Artist)
            .options(joinedload(Artist.albums))
            .where(Artist.link_group_id == group_id, Artist.id != artist.id)
        ).unique().all()
        for a in linked:
            albums.extend(a.albums or [])

    target = _norm(album_title)
    candidate = next((a for a in albums if _norm(a.title) == target), None)
    if not candidate:
        candidate = next(
            (a for a in albums if target and (target in _norm(a.title) or _norm(a.title) in target)),
            None,
        )
    if candidate:
        return candidate

    from app.services.artists import _legacy_id, _unique_provider_album_id

    raw_pid = f"{_slug_id(album_title)}-{track_count}"
    pid = _unique_provider_album_id(
        db,
        provider_name=artist.provider,
        provider_id=raw_pid,
        artist_id=artist.id,
    )
    album = Album(
        provider=artist.provider,
        provider_id=pid,
        deezer_id=_legacy_id(artist.provider, pid),
        artist_id=artist.id,
        title=album_title,
        album_type="album",
        release_date=year,
        cover_url=None,
        track_count=track_count,
        monitored=True,
        status="downloaded",
    )
    db.add(album)
    db.commit()
    db.refresh(album)
    return album


def _upsert_track(
    db: Session,
    album: Album,
    *,
    title: str,
    track_no: int,
    disc_no: int,
    isrc: str | None,
    path: str,
) -> Track:
    tracks = list(album.tracks or [])
    track = None
    if isrc:
        track = next((t for t in tracks if t.isrc and t.isrc == isrc), None)
    if not track and track_no:
        track = next(
            (t for t in tracks if t.track_no == track_no and (t.disc_no or 1) == disc_no),
            None,
        )
    if not track:
        track = next((t for t in tracks if _norm(t.title) == _norm(title)), None)
    if track:
        track.path = path
        if isrc and not track.isrc:
            track.isrc = isrc
        if title and not track.title:
            track.title = title
        if not track.duration:
            try:
                audio = MutagenFile(path)
                length = getattr(getattr(audio, "info", None), "length", None)
                if length and length > 0:
                    track.duration = int(round(float(length)))
            except Exception:  # noqa: BLE001
                pass
        return track

    from app.services.artists import _legacy_id

    duration = 0
    try:
        audio = MutagenFile(path)
        length = getattr(getattr(audio, "info", None), "length", None)
        if length and length > 0:
            duration = int(round(float(length)))
    except Exception:  # noqa: BLE001
        pass

    pid = f"{album.provider_id}-t{disc_no}-{track_no or len(tracks)+1}-{_slug_id(title)[:20]}"
    track = Track(
        provider=album.provider,
        provider_id=pid,
        deezer_id=_legacy_id(album.provider, pid),
        album_id=album.id,
        title=title,
        track_no=track_no or 0,
        disc_no=disc_no or 1,
        duration=duration,
        isrc=isrc,
        path=path,
    )
    db.add(track)
    return track


def import_existing_library(db: Session, *, link_providers: bool = True) -> dict:
    """
    Build Musicarr artists/albums/tracks from files already on disk.
    Optionally link artists to the active streaming provider when a clear name match exists.
    """
    root = library_root(db)
    files = _collect_files(root)
    if not files:
        msg = f"No audio files found under {root}"
        add_history(db, "library_import", msg)
        return {
            "files_seen": 0,
            "artists_created": 0,
            "albums_imported": 0,
            "tracks_linked": 0,
            "provider_linked": 0,
            "message": msg,
        }

    # Group: artist -> album -> files
    grouped: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for f in files:
        grouped[f["artist"]][f["album"]].append(f)

    artists_created = 0
    albums_imported = 0
    tracks_linked = 0
    provider_linked = 0
    known_artists_before = {a.id for a in db.scalars(select(Artist)).all()}

    for artist_name, albums_map in grouped.items():
        artist = _find_artist_by_name(db, artist_name)
        if not artist and link_providers:
            linked = _try_link_provider_artist(db, artist_name)
            if linked:
                artist = linked
                provider_linked += 1
                # Refresh albums from provider without downloading
                db.refresh(artist)
        if not artist:
            # Ambiguous same-name or unknown: create a distinct local row
            sample_path = ""
            for album_files in albums_map.values():
                if album_files:
                    sample_path = str(album_files[0].get("path") or "")
                    break
            artist = _ensure_local_artist(
                db,
                artist_name,
                uniq_key=sample_path or f"{artist_name}:{sorted(albums_map.keys())[0]}",
            )
            if artist.id not in known_artists_before:
                artists_created += 1
                known_artists_before.add(artist.id)

        # Reload albums relationship
        artist = db.scalar(
            select(Artist).options(joinedload(Artist.albums).joinedload(Album.tracks)).where(Artist.id == artist.id)
        )
        assert artist is not None

        for album_title, album_files in albums_map.items():
            year = next((f["year"] for f in album_files if f.get("year")), None)
            existed_ids = {a.id for a in (artist.albums or [])}
            album = _find_or_create_album(
                db,
                artist,
                album_title,
                year=year,
                track_count=len(album_files),
            )
            if album.id not in existed_ids and album.provider == "local":
                albums_imported += 1
            elif album.id not in existed_ids:
                albums_imported += 1

            album = db.scalar(
                select(Album).options(joinedload(Album.tracks)).where(Album.id == album.id)
            )
            assert album is not None

            folder = None
            for f in sorted(album_files, key=lambda x: (x["disc_no"], x["track_no"], x["title"])):
                _upsert_track(
                    db,
                    album,
                    title=f["title"],
                    track_no=f["track_no"],
                    disc_no=f["disc_no"],
                    isrc=f.get("isrc"),
                    path=str(f["path"]),
                )
                tracks_linked += 1
                folder = str(f["path"].parent)

            album.status = "downloaded"
            album.monitored = True
            album.track_count = max(album.track_count or 0, len(album_files))
            if folder:
                album.path = folder
            from app.services.quality import detect_file_quality, quality_rank

            qualities = [detect_file_quality(f["path"]) for f in album_files]
            best = max(qualities, key=quality_rank, default="")
            if best:
                album.quality = best
            db.commit()

    # Pass 2: also run match-only scan for leftover DB tracks
    scan = scan_library(db)

    try:
        from app.services.media_refresh import trigger_media_refresh

        trigger_media_refresh(db, reason="import")
    except Exception:  # noqa: BLE001
        pass

    msg = (
        f"Import complete: {len(files)} files → "
        f"{artists_created} new artists, {albums_imported} albums, "
        f"{tracks_linked} tracks linked"
        + (f", {provider_linked} linked to active provider" if provider_linked else "")
        + f". Scan also matched {scan['matched']} existing DB tracks."
    )
    add_history(db, "library_import", msg)
    return {
        "files_seen": len(files),
        "artists_created": artists_created,
        "albums_imported": albums_imported,
        "tracks_linked": tracks_linked,
        "provider_linked": provider_linked,
        "matched": scan["matched"],
        "unmatched": scan["unmatched"],
        "message": msg,
    }


def scan_library(db: Session) -> dict:
    """Match on-disk files to tracks already in the database (no new artists)."""
    root = library_root(db)
    files = _collect_files(root)
    tracks = db.scalars(select(Track).options(joinedload(Track.album))).all()
    by_isrc = {t.isrc: t for t in tracks if t.isrc}
    by_path = {t.path: t for t in tracks if t.path}
    # album_norm + track_no + disc
    by_album_track: dict[tuple, Track] = {}
    by_album_title: dict[tuple, Track] = {}
    for t in tracks:
        album = t.album
        if not album:
            continue
        key_n = (_norm(album.title), t.track_no or 0, t.disc_no or 1)
        by_album_track[key_n] = t
        by_album_title[(_norm(album.title), _norm(t.title))] = t

    matched = 0
    unmatched = 0

    for f in files:
        sp = str(f["path"])
        if sp in by_path:
            matched += 1
            continue
        track = None
        if f.get("isrc") and f["isrc"] in by_isrc:
            track = by_isrc[f["isrc"]]
        if not track and f.get("album") and f.get("track_no"):
            track = by_album_track.get((_norm(f["album"]), f["track_no"], f["disc_no"] or 1))
        if not track and f.get("album") and f.get("title"):
            track = by_album_title.get((_norm(f["album"]), _norm(f["title"])))
        # Also try artist-aware album title match across DB
        if not track and f.get("album") and f.get("title"):
            album = db.scalar(
                select(Album)
                .options(joinedload(Album.tracks), joinedload(Album.artist))
                .where(Album.title == f["album"])
            )
            if not album:
                albums = db.scalars(select(Album).options(joinedload(Album.tracks))).all()
                album = next((a for a in albums if _norm(a.title) == _norm(f["album"])), None)
            if album:
                if f.get("track_no"):
                    track = next(
                        (
                            t
                            for t in album.tracks
                            if t.track_no == f["track_no"] and (t.disc_no or 1) == (f["disc_no"] or 1)
                        ),
                        None,
                    )
                if not track:
                    track = next(
                        (t for t in album.tracks if _norm(t.title) == _norm(f["title"])),
                        None,
                    )

        if track:
            track.path = sp
            if track.album:
                linked = sum(1 for t in track.album.tracks if t.path)
                if linked >= max(1, (track.album.track_count or len(track.album.tracks)) // 2):
                    track.album.status = "downloaded"
                    track.album.path = str(f["path"].parent)
            matched += 1
        else:
            unmatched += 1

    for album in db.scalars(select(Album).options(joinedload(Album.tracks))).unique().all():
        if not album.tracks:
            continue
        if all(t.path and Path(t.path).exists() for t in album.tracks):
            album.status = "downloaded"
            if not album.path and album.tracks[0].path:
                album.path = str(Path(album.tracks[0].path).parent)
            if not getattr(album, "quality", None):
                from app.services.quality import detect_file_quality, quality_rank

                qualities = [
                    detect_file_quality(Path(t.path))
                    for t in album.tracks
                    if t.path and Path(t.path).exists()
                ]
                best = max(qualities, key=quality_rank, default="")
                if best:
                    album.quality = best

    db.commit()
    msg = f"Scan complete: {len(files)} files, {matched} matched, {unmatched} unmatched"
    add_history(db, "library_scan", msg)
    return {
        "files_seen": len(files),
        "matched": matched,
        "unmatched": unmatched,
        "message": msg,
    }


def build_import_review(db: Session, *, suggest: bool = True) -> dict:
    """List local / weakly tagged artists and albums that need manual linking."""
    from app.models.schemas import ArtistSearchResult, ImportReviewAlbum, ImportReviewArtist

    settings = ensure_settings(db)
    active = (settings.active_provider or "deezer").lower()
    local_rows = list(
        db.scalars(
            select(Artist)
            .options(joinedload(Artist.albums))
            .where(Artist.provider == "local")
            .order_by(Artist.name)
        )
        .unique()
        .all()
    )

    suggestions_cache: dict[str, list] = {}
    local_artists: list[ImportReviewArtist] = []
    for artist in local_rows:
        reason = "Imported as local only (not linked to a download source)"
        if _norm(artist.name) in {"unknown artist", "various artists", ""}:
            reason = "Weak or missing artist tags"
        suggestions: list[ArtistSearchResult] = []
        if suggest and _norm(artist.name) not in {"unknown artist", ""}:
            key = _norm(artist.name)
            if key not in suggestions_cache:
                suggestions_cache[key] = _search_provider_suggestions(db, artist.name, active)
            for hit in suggestions_cache[key][:5]:
                suggestions.append(
                    ArtistSearchResult(
                        provider=active,
                        provider_id=hit.provider_id,
                        deezer_id=int(hit.provider_id)
                        if active == "deezer" and str(hit.provider_id).isdigit()
                        else None,
                        name=hit.name,
                        image_url=hit.image_url,
                        nb_album=hit.nb_album,
                    )
                )
        local_artists.append(
            ImportReviewArtist(
                id=artist.id,
                name=artist.name,
                provider=artist.provider,
                album_count=len(artist.albums or []),
                reason=reason,
                suggestions=suggestions,
            )
        )

    weak_albums: list[ImportReviewAlbum] = []
    albums = (
        db.scalars(select(Album).options(joinedload(Album.artist)).order_by(Album.title))
        .unique()
        .all()
    )
    for album in albums:
        artist = album.artist
        title_n = _norm(album.title)
        artist_n = _norm(artist.name) if artist else ""
        reasons = []
        if title_n in {"unknown album", ""}:
            reasons.append("unknown album title")
        if artist_n in {"unknown artist", ""}:
            reasons.append("unknown artist")
        if album.provider == "local" and not album.cover_url and (album.track_count or 0) == 0:
            reasons.append("no tracks/metadata")
        if not reasons:
            continue
        weak_albums.append(
            ImportReviewAlbum(
                id=album.id,
                title=album.title,
                artist_id=artist.id if artist else 0,
                artist_name=artist.name if artist else "Unknown",
                reason="; ".join(reasons),
            )
        )

    msg = (
        f"{len(local_artists)} local artist(s), {len(weak_albums)} weakly tagged album(s)"
    )
    return {
        "local_artists": local_artists,
        "weak_albums": weak_albums,
        "message": msg,
    }


def _search_provider_suggestions(db: Session, name: str, provider_name: str) -> list:
    try:
        from app.services.providers import get_provider

        provider = get_provider(db, provider_name)
        ok, _ = provider.validate_session()
        if not ok:
            return []
        return list(provider.search_artists(name, limit=8) or [])
    except Exception:  # noqa: BLE001
        return []


def link_local_artist(
    db: Session,
    artist_id: int,
    *,
    provider_id: str,
    provider_name: str | None = None,
) -> Artist:
    """Link an imported local artist to a streaming provider and move on-disk files."""
    from app.services.artists import add_artist

    local = db.scalar(
        select(Artist)
        .options(joinedload(Artist.albums).joinedload(Album.tracks))
        .where(Artist.id == artist_id)
    )
    if not local:
        raise ValueError("Artist not found")

    settings = ensure_settings(db)
    pname = (provider_name or settings.active_provider or "deezer").lower()
    linked = add_artist(
        db,
        str(provider_id),
        monitored=True,
        download_missing=False,
        provider_name=pname,
    )
    # Preserve monitor prefs from local row
    linked.monitor_mode = getattr(local, "monitor_mode", None) or linked.monitor_mode or "all"
    linked.include_singles = getattr(local, "include_singles", None)
    linked.monitored = local.monitored

    linked = db.scalar(
        select(Artist)
        .options(joinedload(Artist.albums).joinedload(Album.tracks))
        .where(Artist.id == linked.id)
    )
    assert linked is not None

    local_albums = list(local.albums or [])
    for local_album in local_albums:
        target = next(
            (
                a
                for a in (linked.albums or [])
                if _norm(a.title) == _norm(local_album.title)
            ),
            None,
        )
        if not target:
            # Reassign album to provider artist if no match
            local_album.artist_id = linked.id
            continue
        # Copy paths onto matching provider album tracks
        if local_album.path and not target.path:
            target.path = local_album.path
        if local_album.status == "downloaded":
            target.status = "downloaded"
        if getattr(local_album, "quality", None) and not getattr(target, "quality", None):
            target.quality = local_album.quality
        local_tracks = list(local_album.tracks or [])
        target_tracks = list(target.tracks or [])
        for lt in local_tracks:
            if not lt.path:
                continue
            match = next(
                (
                    tt
                    for tt in target_tracks
                    if (
                        tt.track_no
                        and lt.track_no
                        and tt.track_no == lt.track_no
                        and (tt.disc_no or 1) == (lt.disc_no or 1)
                    )
                    or _norm(tt.title) == _norm(lt.title)
                ),
                None,
            )
            if match:
                match.path = lt.path
            else:
                lt.album_id = target.id
        if local_album.artist_id == local.id and local.id != linked.id:
            db.delete(local_album)

    if local.id != linked.id and local.provider == "local":
        db.delete(local)

    db.commit()
    add_history(db, "artist_linked", f"Linked {linked.name} to {pname}")
    return linked



def reorganize_library(db: Session) -> dict:
    settings = ensure_settings(db)
    root = library_root(db)
    moved = 0
    skipped = 0
    albums = db.scalars(
        select(Album).options(joinedload(Album.tracks), joinedload(Album.artist))
    ).unique().all()
    for album in albums:
        tracks = [t for t in album.tracks if t.path and Path(t.path).exists()]
        if not tracks:
            skipped += 1
            continue
        artist_name = artist_folder_name(album.artist, db=db) if album.artist else "Unknown Artist"
        dest_folder = build_album_folder(
            root,
            settings.folder_template,
            artist=artist_name,
            album=album.title,
            year=year_from_release(album.release_date),
            album_type=album.album_type,
        )
        dest_folder.mkdir(parents=True, exist_ok=True)
        for track in tracks:
            src = Path(track.path)
            filename = build_track_filename(
                settings.track_template,
                title=track.title,
                track=track.track_no or 0,
                disc=track.disc_no or 1,
                artist=artist_name,
                album=album.title,
                ext=src.suffix.lower(),
            )
            dest = dest_folder / filename
            if src.resolve() == dest.resolve():
                continue
            if dest.exists() and src.resolve() != dest.resolve():
                skipped += 1
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            src.rename(dest)
            track.path = str(dest)
            moved += 1
        album.path = str(dest_folder)
    db.commit()
    msg = f"Reorganized library: moved {moved}, skipped {skipped}"
    add_history(db, "reorganize", msg)
    return {"moved": moved, "skipped": skipped, "message": msg}
