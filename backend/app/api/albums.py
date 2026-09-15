from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.models import Album, Track
from app.models.schemas import AlbumOut, AlbumPatch, TrackOut
from app.services.download_queue import download_queue
from app.services.filters import is_junk_title, is_live_title
from app.services.history import add_history
from app.services.settings_service import ensure_settings

router = APIRouter(prefix="/albums", tags=["albums"])


def _active_provider(db: Session) -> str:
    return (ensure_settings(db).active_provider or "deezer").lower()


def _album_out(
    album: Album,
    include_tracks: bool = True,
    *,
    target_bitrate: str = "flac",
    upgrade_enabled: bool = True,
) -> AlbumOut:
    from app.services.quality import needs_upgrade

    tracks = []
    if include_tracks:
        tracks = [
            TrackOut(
                id=t.id,
                provider=getattr(t, "provider", "deezer") or "deezer",
                provider_id=getattr(t, "provider_id", "") or "",
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
    quality = getattr(album, "quality", "") or ""
    upgradable = bool(
        upgrade_enabled
        and album.status == "downloaded"
        and album.provider != "local"
        and needs_upgrade(quality, target_bitrate)
    )
    return AlbumOut(
        id=album.id,
        provider=getattr(album, "provider", "deezer") or "deezer",
        provider_id=getattr(album, "provider_id", "") or "",
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
        artist_name=album.artist.name if getattr(album, "artist", None) else None,
        sources=[(getattr(album, "provider", None) or "deezer").lower()],
        tracks=tracks,
    )


def _quality_settings(db: Session) -> tuple[str, bool]:
    s = ensure_settings(db)
    return (s.bitrate or "flac").lower(), bool(getattr(s, "upgrade_enabled", True))


@router.get("/wanted", response_model=list[AlbumOut])
def wanted_albums(
    db: Session = Depends(get_db),
    album_type: str | None = None,
):
    active = _active_provider(db)
    q = (
        select(Album)
        .options(joinedload(Album.tracks), joinedload(Album.artist))
        .where(
            Album.status == "wanted",
            Album.monitored.is_(True),
            Album.provider == active,
        )
        .order_by(Album.release_date.desc())
    )
    albums = db.scalars(q).unique().all()
    if album_type:
        albums = [a for a in albums if (a.album_type or "").lower() == album_type.lower()]
    target, up_on = _quality_settings(db)
    return [_album_out(a, target_bitrate=target, upgrade_enabled=up_on) for a in albums]


class BulkIds(BaseModel):
    album_ids: list[int]


@router.post("/wanted/download-all")
def download_all_wanted(
    db: Session = Depends(get_db)
):
    active = _active_provider(db)
    albums = db.scalars(
        select(Album).where(
            Album.status == "wanted",
            Album.monitored.is_(True),
            Album.provider == active,
        )
    ).all()
    queued = 0
    for album in albums:
        if download_queue.enqueue_album(db, album.id):
            queued += 1
    return {"queued": queued}


@router.post("/wanted/skip-all")
def skip_all_wanted(db: Session = Depends(get_db)):
    active = _active_provider(db)
    albums = db.scalars(
        select(Album).where(
            Album.status == "wanted",
            Album.monitored.is_(True),
            Album.provider == active,
        )
    ).all()
    for album in albums:
        album.status = "skipped"
        album.monitored = False
    db.commit()
    return {"skipped": len(albums)}


@router.post("/wanted/skip-singles")
def skip_all_singles(db: Session = Depends(get_db)):
    active = _active_provider(db)
    albums = db.scalars(
        select(Album).where(
            Album.status == "wanted",
            Album.monitored.is_(True),
            Album.provider == active,
            Album.album_type == "single",
        )
    ).all()
    for album in albums:
        album.status = "skipped"
        album.monitored = False
    db.commit()
    return {"skipped": len(albums)}


@router.post("/wanted/skip-junk")
def skip_junk_wanted(db: Session = Depends(get_db)):
    active = _active_provider(db)
    settings = ensure_settings(db)
    albums = db.scalars(
        select(Album).where(
            Album.status == "wanted",
            Album.monitored.is_(True),
            Album.provider == active,
        )
    ).all()
    skipped = 0
    for album in albums:
        junk = is_junk_title(album.title or "")
        live = getattr(settings, "ignore_live_releases", False) and is_live_title(
            album.title or ""
        )
        if junk or live:
            album.status = "skipped"
            album.monitored = False
            skipped += 1
    db.commit()
    return {"skipped": skipped}


@router.post("/bulk/skip")
def bulk_skip(payload: BulkIds, db: Session = Depends(get_db)):
    count = 0
    for album_id in payload.album_ids:
        album = db.get(Album, album_id)
        if album:
            album.status = "skipped"
            album.monitored = False
            count += 1
    db.commit()
    return {"skipped": count}


@router.post("/bulk/download")
def bulk_download(
    payload: BulkIds,
    db: Session = Depends(get_db)
):
    queued = 0
    for album_id in payload.album_ids:
        album = db.get(Album, album_id)
        if album and album.status == "skipped":
            album.status = "wanted"
            album.monitored = True
        if download_queue.enqueue_album(db, album_id):
            queued += 1
    db.commit()
    return {"queued": queued}


@router.get("/upgradable", response_model=list[AlbumOut])
def upgradable_albums(db: Session = Depends(get_db)):
    from app.services.quality import needs_upgrade

    target, up_on = _quality_settings(db)
    if not up_on:
        return []
    active = _active_provider(db)
    albums = (
        db.scalars(
            select(Album)
            .options(joinedload(Album.tracks), joinedload(Album.artist))
            .where(Album.status == "downloaded", Album.provider == active)
        )
        .unique()
        .all()
    )
    out = []
    for a in albums:
        if a.provider == "local":
            continue
        q = getattr(a, "quality", "") or ""
        if needs_upgrade(q, target):
            out.append(_album_out(a, target_bitrate=target, upgrade_enabled=up_on))
    return out


@router.post("/upgrade-all")
def upgrade_all(
    db: Session = Depends(get_db)
):
    from app.services.quality import needs_upgrade

    target, up_on = _quality_settings(db)
    if not up_on:
        return {"queued": 0, "message": "Upgrades disabled in settings"}
    active = _active_provider(db)
    albums = db.scalars(
        select(Album).where(Album.status == "downloaded", Album.provider == active)
    ).all()
    queued = 0
    for album in albums:
        if album.provider == "local":
            continue
        if needs_upgrade(getattr(album, "quality", "") or "", target):
            if download_queue.enqueue_album(
                db, album.id, allow_upgrade=True
            ):
                queued += 1
    return {"queued": queued, "target": target}


@router.get("/{album_id}", response_model=AlbumOut)
def get_album(album_id: int, db: Session = Depends(get_db)):
    album = db.scalar(
        select(Album)
        .options(joinedload(Album.tracks), joinedload(Album.artist))
        .where(Album.id == album_id)
    )
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")
    if not album.tracks:
        try:
            from app.services.artists import sync_album_tracks

            sync_album_tracks(db, album)
            album = db.scalar(
                select(Album)
                .options(joinedload(Album.tracks), joinedload(Album.artist))
                .where(Album.id == album_id)
            )
        except Exception:  # noqa: BLE001
            pass
    target, up_on = _quality_settings(db)
    return _album_out(album, target_bitrate=target, upgrade_enabled=up_on)


@router.patch("/{album_id}", response_model=AlbumOut)
def patch_album(album_id: int, payload: AlbumPatch, db: Session = Depends(get_db)):
    album = db.scalar(
        select(Album)
        .options(joinedload(Album.tracks), joinedload(Album.artist))
        .where(Album.id == album_id)
    )
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(album, key, value)
    db.commit()
    db.refresh(album)
    target, up_on = _quality_settings(db)
    return _album_out(album, target_bitrate=target, upgrade_enabled=up_on)


@router.post("/{album_id}/download")
def download_album(
    album_id: int,
    db: Session = Depends(get_db),
    upgrade: bool = False
):
    album = db.get(Album, album_id)
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")
    if album.status == "skipped" or upgrade:
        album.status = "wanted"
        album.monitored = True
        db.commit()
    job = download_queue.enqueue_album(
        db,
        album_id,
        allow_upgrade=upgrade or album.status == "downloaded",
            )
    return {
        "queued": bool(job),
        "job_id": job.id if job else None,
        "source": job.source if job else None,
    }


@router.delete("/{album_id}")
def delete_album(
    album_id: int,
    db: Session = Depends(get_db),
    delete_files: bool = Query(False),
):
    import shutil
    from pathlib import Path

    album = db.scalar(
        select(Album).options(joinedload(Album.tracks)).where(Album.id == album_id)
    )
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")
    title = album.title
    if delete_files and album.path:
        folder = Path(album.path)
        if folder.exists() and folder.is_dir():
            shutil.rmtree(folder, ignore_errors=True)
        for track in album.tracks or []:
            if track.path:
                p = Path(track.path)
                if p.exists() and p.is_file():
                    p.unlink(missing_ok=True)
    db.delete(album)
    db.commit()
    add_history(db, "album_removed", f"Removed album {title}" + (" (+files)" if delete_files else ""))
    return {"ok": True, "deleted_files": delete_files}
