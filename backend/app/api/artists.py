from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.schemas import ArtistCreate, ArtistOut, ArtistPatch, ArtistSearchResult
from app.services.artists import (
    add_artist,
    delete_linked_artists,
    find_linked_artists,
    get_artist_detail,
    grouped_artist_stats,
    list_artists_grouped,
    merge_album_rows,
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
) -> ArtistOut:
    if not artists:
        raise ValueError("empty artist group")
    primary = min(artists, key=lambda a: a.id)
    total, downloaded, wanted = grouped_artist_stats(artists, active_provider=active)
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
        added_at=min(a.added_at for a in artists),
        last_synced_at=max((a.last_synced_at for a in artists if a.last_synced_at), default=None),
        album_count=total,
        downloaded_count=downloaded,
        wanted_count=wanted,
        providers=providers,
        linked_artist_ids=linked_ids,
        albums=albums,
    )


@router.get("/search", response_model=list[ArtistSearchResult])
def search_artists(q: str = Query(..., min_length=1), limit: int = 25, db: Session = Depends(get_db)):
    try:
        provider = get_active_provider(db)
        results = provider.search_artists(q, limit=limit)
    except ProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    out = []
    for r in results:
        out.append(
            ArtistSearchResult(
                provider=provider.name,
                provider_id=r.provider_id,
                deezer_id=int(r.provider_id) if provider.name == "deezer" and r.provider_id.isdigit() else None,
                name=r.name,
                image_url=r.image_url,
                nb_album=r.nb_album,
            )
        )
    return out


@router.get("", response_model=list[ArtistOut])
def get_artists(db: Session = Depends(get_db)):
    settings = ensure_settings(db)
    active = (settings.active_provider or "deezer").lower()
    target = (settings.bitrate or "flac").lower()
    up_on = bool(getattr(settings, "upgrade_enabled", True))
    return [
        _artist_group_out(
            group,
            include_albums=False,
            active=active,
            target_bitrate=target,
            upgrade_enabled=up_on,
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
        )
    except ProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    detail = get_artist_detail(db, artist.id)
    linked = find_linked_artists(db, detail or artist)
    return _artist_group_out(
        linked,
        include_albums=True,
        active=active,
        target_bitrate=(settings.bitrate or "flac").lower(),
        upgrade_enabled=bool(getattr(settings, "upgrade_enabled", True)),
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
    )


@router.patch("/{artist_id}", response_model=ArtistOut)
def patch_artist(artist_id: int, payload: ArtistPatch, db: Session = Depends(get_db)):
    artist = get_artist_detail(db, artist_id)
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")
    linked = find_linked_artists(db, artist)
    data = payload.model_dump(exclude_unset=True)
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
    )


@router.delete("/{artist_id}")
def remove_artist(artist_id: int, db: Session = Depends(get_db)):
    if not delete_linked_artists(db, artist_id):
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
        try:
            if row.provider == "local":
                continue
            provider = get_provider(db, row.provider)
            ok, err = provider.validate_session()
            if not ok:
                errors.append(f"{row.provider}: {err or 'not connected'}")
                continue
            sync_artist_albums(db, row)
        except ProviderError as exc:
            errors.append(f"{row.provider}: {exc}")
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
    )
    if errors and not any(True for _ in linked):
        raise HTTPException(status_code=400, detail="; ".join(errors))
    return out


@router.post("/{artist_id}/download-missing")
def download_missing(artist_id: int, db: Session = Depends(get_db)):
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
