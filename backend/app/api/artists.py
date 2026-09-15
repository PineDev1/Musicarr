from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Artist
from app.models.schemas import (
    ArtistCreate,
    ArtistOut,
    ArtistPatch,
    ArtistSearchResult,
)
from app.services.artists import (
    add_artist,
    delete_artist,
    find_linked_artists,
    get_artist_detail,
    grouped_artist_stats,
    list_artists_grouped,
    merge_album_rows,
    name_collision_ids,
    sync_artist_albums,
)
from app.services.download_queue import download_queue
from app.services.providers import get_active_provider, get_provider
from app.services.providers.base import ProviderError
from app.services.settings_service import ensure_settings

router = APIRouter(prefix="/artists", tags=["artists"])


def _album_out(album, sources: list[str] | None = None, include_tracks: bool = True, *, target_bitrate: str = "flac", upgrade_enabled: bool = True):
    from app.models.schemas import AlbumOut, TrackOut
    from app.services.quality import needs_upgrade

    tracks = []
    if include_tracks:
        tracks = [
            TrackOut(
                id=t.id,
                provider=t.provider,
                provider_id=t.provider_id,
                deezer_id=t.deezer_id,
                title=t.title,
                track_no=t.track_no,
                disc_no=t.disc_no,
                duration=t.duration,
                path=t.path,
                downloaded=bool(t.path),
            )
            for t in sorted(album.tracks or [], key=lambda x: (x.disc_no, x.track_no))
        ]
    src = sources or [(album.provider or "deezer").lower()]
    quality = getattr(album, "quality", "") or ""
    upgradable = bool(
        upgrade_enabled
        and album.status == "downloaded"
        and album.provider != "local"
        and needs_upgrade(quality, target_bitrate)
    )
    return AlbumOut(
        id=album.id,
        provider=album.provider,
        provider_id=album.provider_id,
        deezer_id=album.deezer_id,
        artist_id=album.artist_id,
        title=album.title,
        album_type=album.album_type,
        release_date=album.release_date,
        cover_url=album.cover_url,
        track_count=album.track_count,
        monitored=album.monitored,
        status=album.status,
        status_reason=getattr(album, "status_reason", "") or "",
        musicbrainz_id=getattr(album, "musicbrainz_id", None),
        artist_credit=getattr(album, "artist_credit", "") or "",
        path=album.path,
        quality=quality,
        upgrade_available=upgradable,
        sources=src,
        tracks=tracks,
    )


def _artist_group_out(
    artists: list,
    *,
    include_albums: bool = False,
    active: str = "deezer",
    target_bitrate: str = "flac",
    upgrade_enabled: bool = True,
    collision_ids: set[int] | None = None,
) -> ArtistOut:
    if not artists:
        raise ValueError("empty artist group")
    primary = min(artists, key=lambda a: a.id)
    total, downloaded, wanted, missing = grouped_artist_stats(artists, active_provider=active)
    providers = sorted({(a.provider or "deezer").lower() for a in artists})
    linked_ids = [a.id for a in sorted(artists, key=lambda a: a.id)]
    image = next((a.image_url for a in artists if a.image_url), None)
    albums = []
    if include_albums:
        all_albums = []
        for artist in artists:
            all_albums.extend(artist.albums or [])
        for album, sources in merge_album_rows(all_albums, active_provider=active):
            albums.append(
                _album_out(
                    album,
                    sources=sources,
                    include_tracks=True,
                    target_bitrate=target_bitrate,
                    upgrade_enabled=upgrade_enabled,
                )
            )
    collided = False
    if collision_ids is not None:
        collided = any(a.id in collision_ids for a in artists)
    related = []
    import json

    from app.models.schemas import RelatedArtistOut

    for a in artists:
        raw = getattr(a, "related_artists_json", None) or "[]"
        try:
            payload = json.loads(raw) if isinstance(raw, str) else (raw or [])
        except json.JSONDecodeError:
            payload = []
        for item in payload:
            if not isinstance(item, dict) or not item.get("name"):
                continue
            related.append(
                RelatedArtistOut(
                    id=item.get("id"),
                    name=item["name"],
                    musicbrainz_id=item.get("musicbrainz_id"),
                    provider=item.get("provider"),
                )
            )
    # de-dupe by name
    seen_rel: set[str] = set()
    related_unique: list = []
    for r in related:
        key = r.name.strip().lower()
        if key in seen_rel:
            continue
        seen_rel.add(key)
        related_unique.append(r)
    return ArtistOut(
        id=primary.id,
        provider=primary.provider,
        provider_id=primary.provider_id,
        deezer_id=primary.deezer_id,
        name=primary.name,
        image_url=image,
        monitored=any(a.monitored for a in artists),
        monitor_mode=getattr(primary, "monitor_mode", None) or "all",
        include_singles=getattr(primary, "include_singles", None),
        musicbrainz_id=next(
            (
                (getattr(a, "musicbrainz_id", None) or "").strip()
                for a in artists
                if (getattr(a, "musicbrainz_id", None) or "").strip()
            ),
            None,
        ),
        added_at=min(a.added_at for a in artists),
        last_synced_at=max((a.last_synced_at for a in artists if a.last_synced_at), default=None),
        album_count=total,
        downloaded_count=downloaded,
        wanted_count=wanted,
        missing_count=missing,
        providers=providers,
        linked_artist_ids=linked_ids,
        related_artists=related_unique,
        name_collision=collided,
        albums=albums,
    )


@router.get("/search", response_model=list[ArtistSearchResult])
def search_artists(q: str = Query(..., min_length=1), limit: int = 25, db: Session = Depends(get_db)):
    try:
        provider = get_active_provider(db)
        results = provider.search_artists(q, limit=limit)
    except ProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    from app.services import musicbrainz

    # Prefer MusicBrainz catalog counts (local when Ready) over provider album totals.
    mb_counts: dict[str, int | None] = {}
    out = []
    for r in results:
        name_key = (r.name or "").strip().lower()
        mb_count: int | None = None
        if name_key:
            if name_key not in mb_counts:
                mbid = musicbrainz.resolve_artist(r.name)
                mb_counts[name_key] = (
                    musicbrainz.count_release_groups(mbid) if mbid else None
                )
            mb_count = mb_counts[name_key]
        out.append(
            ArtistSearchResult(
                provider=provider.name,
                provider_id=r.provider_id,
                deezer_id=int(r.provider_id) if provider.name == "deezer" and r.provider_id.isdigit() else None,
                name=r.name,
                image_url=r.image_url,
                nb_album=mb_count if mb_count is not None else r.nb_album,
            )
        )
    return out


@router.get("", response_model=list[ArtistOut])
def get_artists(db: Session = Depends(get_db)):
    settings = ensure_settings(db)
    active = (settings.active_provider or "deezer").lower()
    target = (settings.bitrate or "flac").lower()
    up_on = bool(getattr(settings, "upgrade_enabled", True))
    collisions = name_collision_ids(db)
    return [
        _artist_group_out(
            group,
            include_albums=False,
            active=active,
            target_bitrate=target,
            upgrade_enabled=up_on,
            collision_ids=collisions,
        )
        for group in list_artists_grouped(db)
    ]


@router.post("", response_model=ArtistOut)
def create_artist(payload: ArtistCreate, db: Session = Depends(get_db)):
    provider_id = payload.provider_id
    if not provider_id and payload.deezer_id is not None:
        provider_id = str(payload.deezer_id)
    if not provider_id:
        raise HTTPException(status_code=400, detail="provider_id required")
    settings = ensure_settings(db)
    active = (settings.active_provider or "deezer").lower()
    try:
        artist = add_artist(
            db,
            provider_id,
            monitored=payload.monitored,
            download_missing=payload.download_missing,
            provider_name=payload.provider or settings.active_provider,
            include_singles=payload.include_singles,
        )
    except ProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Failed to add artist: {exc}") from exc
    detail = get_artist_detail(db, artist.id)
    if not detail:
        raise HTTPException(status_code=404, detail="Artist was deleted during sync")
    linked = find_linked_artists(db, detail)
    return _artist_group_out(
        linked,
        include_albums=True,
        active=active,
        target_bitrate=(settings.bitrate or "flac").lower(),
        upgrade_enabled=bool(getattr(settings, "upgrade_enabled", True)),
        collision_ids=name_collision_ids(db),
    )


@router.get("/{artist_id}", response_model=ArtistOut)
def get_artist(artist_id: int, db: Session = Depends(get_db)):
    artist = get_artist_detail(db, artist_id)
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")
    settings = ensure_settings(db)
    active = (settings.active_provider or "deezer").lower()
    linked = find_linked_artists(db, artist)
    return _artist_group_out(
        linked,
        include_albums=True,
        active=active,
        target_bitrate=(settings.bitrate or "flac").lower(),
        upgrade_enabled=bool(getattr(settings, "upgrade_enabled", True)),
        collision_ids=name_collision_ids(db),
    )


@router.patch("/{artist_id}", response_model=ArtistOut)
def patch_artist(artist_id: int, payload: ArtistPatch, db: Session = Depends(get_db)):
    artist = get_artist_detail(db, artist_id)
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")
    linked = find_linked_artists(db, artist)
    data = payload.model_dump(exclude_unset=True)
    singles_changed = "include_singles" in data
    for row in linked:
        for key, value in data.items():
            setattr(row, key, value)
        # Convenience: monitor_mode none => unmonitor; monitored False => mode none
        if "monitored" in data and data["monitored"] is False:
            row.monitor_mode = "none"
        if "monitor_mode" in data and data["monitor_mode"] == "none":
            row.monitored = False
        if "monitor_mode" in data and data["monitor_mode"] in {"all", "new"}:
            row.monitored = True
    db.commit()

    # Lidarr-style: changing singles preference rescans MusicBrainz and queues new wanted
    if singles_changed:
        for row in linked:
            try:
                if row.provider == "local":
                    continue
                sync_artist_albums(db, row)
                if row.monitored and (getattr(row, "monitor_mode", "all") or "all") != "none":
                    download_queue.enqueue_artist_missing(db, row.id)
            except ProviderError:
                db.rollback()
            except Exception:  # noqa: BLE001
                db.rollback()

    settings = ensure_settings(db)
    active = (settings.active_provider or "deezer").lower()
    artist = get_artist_detail(db, artist_id)
    linked = find_linked_artists(db, artist)
    return _artist_group_out(
        linked,
        include_albums=True,
        active=active,
        target_bitrate=(settings.bitrate or "flac").lower(),
        upgrade_enabled=bool(getattr(settings, "upgrade_enabled", True)),
        collision_ids=name_collision_ids(db),
    )


@router.delete("/{artist_id}")
def remove_artist(artist_id: int, db: Session = Depends(get_db)):
    if not delete_artist(db, artist_id):
        raise HTTPException(status_code=404, detail="Artist not found")
    return {"ok": True}


@router.post("/{artist_id}/refresh", response_model=ArtistOut)
def refresh_artist(artist_id: int, db: Session = Depends(get_db)):
    artist = get_artist_detail(db, artist_id)
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")
    linked = find_linked_artists(db, artist)
    errors: list[str] = []
    for row in linked:
        provider_name = getattr(row, "provider", None) or "?"
        artist_row_id = getattr(row, "id", None)
        try:
            if provider_name == "local":
                continue
            provider = get_provider(db, provider_name)
            ok, err = provider.validate_session()
            if not ok:
                errors.append(f"{provider_name}: {err or 'not connected'}")
                continue
            # Re-load in case the artist was deleted mid-request
            fresh = db.get(Artist, artist_row_id) if artist_row_id else None
            if not fresh:
                errors.append(f"{provider_name}: artist was deleted")
                continue
            sync_artist_albums(db, fresh)
        except ProviderError as exc:
            db.rollback()
            errors.append(f"{provider_name}: {exc}")
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            errors.append(f"{provider_name}: {exc}")
    artist = get_artist_detail(db, artist_id)
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")
    settings = ensure_settings(db)
    active = (settings.active_provider or "deezer").lower()
    linked = find_linked_artists(db, artist)
    out = _artist_group_out(
        linked,
        include_albums=True,
        active=active,
        target_bitrate=(settings.bitrate or "flac").lower(),
        upgrade_enabled=bool(getattr(settings, "upgrade_enabled", True)),
        collision_ids=name_collision_ids(db),
    )
    if errors and not any(True for _ in linked):
        raise HTTPException(status_code=400, detail="; ".join(errors))
    return out


@router.post("/{artist_id}/download-missing")
def download_missing(
    artist_id: int,
    db: Session = Depends(get_db)
):
    artist = get_artist_detail(db, artist_id)
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")
    active = (ensure_settings(db).active_provider or "deezer").lower()
    linked = find_linked_artists(db, artist)
    queued = 0
    for row in linked:
        if (row.provider or "").lower() != active:
            continue
        jobs = download_queue.enqueue_artist_missing(db, row.id)
        queued += len(jobs)
    return {"queued": queued}
