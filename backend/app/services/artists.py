from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import Album, Artist, Track
from app.services.history import add_history
from app.services.providers import get_active_provider
from app.services.providers.base import ProviderError
from app.services.settings_service import ensure_settings


def _legacy_id(provider: str, provider_id: str) -> int:
    """Keep legacy deezer_id column unique for older SQLite indexes."""
    if provider == "deezer" and str(provider_id).isdigit():
        return int(provider_id)
    return abs(hash(f"{provider}:{provider_id}")) % 2_000_000_000


def album_type_allowed_for_artist(db: Session, artist: Artist, album_type: str) -> bool:
    settings = ensure_settings(db)
    if album_type == "single":
        # Per-artist override: False blocks singles; True allows; None inherits global
        override = getattr(artist, "include_singles", None)
        if override is False:
            return False
        if override is True:
            return True
    mapping = {
        "album": settings.include_albums,
        "ep": settings.include_eps,
        "single": settings.include_singles,
        "compilation": settings.include_compilations,
    }
    return mapping.get(album_type, False)


def sync_artist_albums(db: Session, artist: Artist) -> list[Album]:
    from app.services.filters import is_junk_title, is_live_title

    if not artist.monitored or (getattr(artist, "monitor_mode", "all") or "all") == "none":
        return list(
            db.scalars(select(Album).where(Album.artist_id == artist.id)).all()
        )

    if artist.provider == "local":
        return list(
            db.scalars(select(Album).where(Album.artist_id == artist.id)).all()
        )

    provider = get_active_provider(db)
    if artist.provider != provider.name:
        from app.services.providers import get_provider

        provider = get_provider(db, artist.provider)

    settings = ensure_settings(db)
    raw_albums = provider.list_albums(artist.provider_id)
    existing = {
        a.provider_id: a
        for a in db.scalars(select(Album).where(Album.artist_id == artist.id)).all()
    }
    monitor_mode = (getattr(artist, "monitor_mode", None) or "all").lower()
    cutoff = artist.added_at
    touched: list[Album] = []
    for raw in raw_albums:
        pid = raw.provider_id
        if pid in existing:
            album = existing[pid]
            album.title = raw.title or album.title
            album.cover_url = raw.cover_url or album.cover_url
            album.release_date = raw.release_date or album.release_date
            album.track_count = raw.track_count or album.track_count
            album.album_type = raw.album_type
            touched.append(album)
            continue
        if not album_type_allowed_for_artist(db, artist, raw.album_type):
            continue
        if getattr(settings, "ignore_junk_titles", True) and is_junk_title(raw.title or ""):
            continue
        if getattr(settings, "ignore_live_releases", False) and is_live_title(raw.title or ""):
            continue
        min_tracks = int(getattr(settings, "min_track_count", 0) or 0)
        if min_tracks > 0 and (raw.track_count or 0) > 0 and raw.track_count < min_tracks:
            if raw.album_type in {"album", "ep", "compilation"}:
                continue
        if monitor_mode == "new" and raw.release_date and cutoff:
            try:
                from datetime import date as date_cls

                rd = date_cls.fromisoformat(raw.release_date[:10])
                added = cutoff.date() if hasattr(cutoff, "date") else cutoff
                if rd < added:
                    continue
            except ValueError:
                pass

        album = Album(
            provider=artist.provider,
            provider_id=pid,
            deezer_id=_legacy_id(artist.provider, pid),
            artist_id=artist.id,
            title=raw.title,
            album_type=raw.album_type,
            release_date=raw.release_date,
            cover_url=raw.cover_url,
            track_count=raw.track_count,
            monitored=True,
            status="wanted",
        )
        db.add(album)
        touched.append(album)
    artist.last_synced_at = datetime.now(timezone.utc)
    db.commit()
    for album in touched:
        db.refresh(album)
    return touched


def sync_album_tracks(db: Session, album: Album) -> list[Track]:
    from app.services.providers import get_provider

    provider = get_provider(db, album.provider)
    raw_tracks = provider.list_tracks(album.provider_id)
    existing = {t.provider_id: t for t in album.tracks}
    result: list[Track] = []
    for raw in raw_tracks:
        if raw.provider_id in existing:
            track = existing[raw.provider_id]
            track.title = raw.title or track.title
            track.track_no = raw.track_no or track.track_no
            track.disc_no = raw.disc_no or track.disc_no
            track.duration = raw.duration or track.duration
            track.isrc = raw.isrc or track.isrc
            result.append(track)
            continue
        track = Track(
            provider=album.provider,
            provider_id=raw.provider_id,
            deezer_id=_legacy_id(album.provider, raw.provider_id),
            album_id=album.id,
            title=raw.title,
            track_no=raw.track_no,
            disc_no=raw.disc_no,
            duration=raw.duration,
            isrc=raw.isrc,
        )
        db.add(track)
        result.append(track)
    album.track_count = len(result) or album.track_count
    db.commit()
    return result


def add_artist(
    db: Session,
    provider_id: str,
    *,
    monitored: bool = True,
    download_missing: bool = True,
    provider_name: str | None = None,
) -> Artist:
    settings = ensure_settings(db)
    pname = (provider_name or settings.active_provider or "deezer").lower()
    from app.services.providers import get_provider

    provider = get_provider(db, pname)

    existing = db.scalar(
        select(Artist).where(Artist.provider == pname, Artist.provider_id == str(provider_id))
    )
    if existing:
        sync_artist_albums(db, existing)
        return existing

    try:
        meta = provider.get_artist(str(provider_id))
    except ProviderError:
        raise

    artist = Artist(
        provider=pname,
        provider_id=str(provider_id),
        deezer_id=_legacy_id(pname, str(provider_id)),
        name=meta.name,
        image_url=meta.image_url,
        monitored=monitored,
    )
    db.add(artist)
    db.commit()
    db.refresh(artist)
    add_history(db, "artist_added", f"Added artist {artist.name} ({pname})")
    sync_artist_albums(db, artist)
    db.refresh(artist)
    if download_missing and monitored:
        from app.services.download_queue import download_queue

        download_queue.enqueue_artist_missing(db, artist.id)
    return artist


def get_artist_detail(db: Session, artist_id: int) -> Artist | None:
    return db.scalar(
        select(Artist)
        .options(joinedload(Artist.albums).joinedload(Album.tracks))
        .where(Artist.id == artist_id)
    )


def list_artists(db: Session) -> list[Artist]:
    return list(
        db.scalars(
            select(Artist).options(joinedload(Artist.albums)).order_by(Artist.name)
        )
        .unique()
        .all()
    )


def delete_artist(db: Session, artist_id: int) -> bool:
    artist = db.get(Artist, artist_id)
    if not artist:
        return False
    name = artist.name
    db.delete(artist)
    db.commit()
    add_history(db, "artist_removed", f"Removed artist {name}")
    return True


def artist_stats(artist: Artist) -> tuple[int, int, int]:
    albums = artist.albums or []
    total = len(albums)
    downloaded = sum(1 for a in albums if a.status == "downloaded")
    wanted = sum(1 for a in albums if a.status == "wanted" and a.monitored)
    return total, downloaded, wanted


def _norm_artist_name(name: str) -> str:
    return " ".join((name or "").strip().lower().split())


def _norm_album_title(title: str) -> str:
    import re

    t = (title or "").lower().strip()
    t = re.sub(r"\([^)]*\)", "", t)
    t = re.sub(r"\[[^\]]*\]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def find_linked_artists(db: Session, artist: Artist) -> list[Artist]:
    """All local artist rows that share the same display name (any provider)."""
    key = _norm_artist_name(artist.name)
    rows = (
        db.scalars(
            select(Artist)
            .options(joinedload(Artist.albums).joinedload(Album.tracks))
            .order_by(Artist.id)
        )
        .unique()
        .all()
    )
    return [a for a in rows if _norm_artist_name(a.name) == key]


def _status_rank(status: str) -> int:
    return {"downloaded": 0, "wanted": 1, "skipped": 2}.get(status or "", 9)


def merge_album_rows(
    albums: list[Album],
    *,
    active_provider: str = "deezer",
) -> list[tuple[Album, list[str]]]:
    """Collapse same-title albums across providers; keep best status row + source list."""
    groups: dict[str, list[Album]] = {}
    for album in albums:
        groups.setdefault(_norm_album_title(album.title) or f"id:{album.id}", []).append(album)

    merged: list[tuple[Album, list[str]]] = []
    for group in groups.values():
        sources = sorted({(a.provider or "deezer").lower() for a in group})
        group_sorted = sorted(
            group,
            key=lambda a: (
                _status_rank(a.status),
                0 if (a.provider or "").lower() == active_provider else 1,
                -(a.track_count or 0),
                a.id,
            ),
        )
        merged.append((group_sorted[0], sources))
    merged.sort(key=lambda item: (item[0].release_date or "", item[0].title), reverse=True)
    return merged


def grouped_artist_stats(artists: list[Artist], active_provider: str = "deezer") -> tuple[int, int, int]:
    all_albums: list[Album] = []
    for artist in artists:
        all_albums.extend(artist.albums or [])
    merged = merge_album_rows(all_albums, active_provider=active_provider)
    total = len(merged)
    downloaded = sum(1 for album, _ in merged if album.status == "downloaded")
    wanted = sum(1 for album, _ in merged if album.status == "wanted" and album.monitored)
    return total, downloaded, wanted


def list_artists_grouped(db: Session) -> list[list[Artist]]:
    artists = list_artists(db)
    buckets: dict[str, list[Artist]] = {}
    order: list[str] = []
    for artist in artists:
        key = _norm_artist_name(artist.name) or f"id:{artist.id}"
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(artist)
    return [buckets[k] for k in order]


def delete_linked_artists(db: Session, artist_id: int) -> bool:
    artist = db.get(Artist, artist_id)
    if not artist:
        return False
    linked = find_linked_artists(db, artist)
    name = artist.name
    for row in linked:
        db.delete(row)
    db.commit()
    add_history(db, "artist_removed", f"Removed artist {name} ({len(linked)} source(s))")
    return True
