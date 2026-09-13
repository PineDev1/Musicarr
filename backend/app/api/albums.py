from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.models import Album
from app.models.schemas import AlbumOut, AlbumPatch, TrackOut
from app.services.download_queue import download_queue
from app.services.settings_service import ensure_settings

router = APIRouter(prefix="/albums", tags=["albums"])


def _active_provider(db: Session) -> str:
    return (ensure_settings(db).active_provider or "deezer").lower()


def _album_out(album: Album, include_tracks: bool = True) -> AlbumOut:
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
        path=album.path,
        artist_name=album.artist.name if getattr(album, "artist", None) else None,
        sources=[(getattr(album, "provider", None) or "deezer").lower()],
        tracks=tracks,
    )


@router.get("/wanted", response_model=list[AlbumOut])
def wanted_albums(db: Session = Depends(get_db)):
    active = _active_provider(db)
    albums = (
        db.scalars(
            select(Album)
            .options(joinedload(Album.tracks), joinedload(Album.artist))
            .where(
                Album.status == "wanted",
                Album.monitored.is_(True),
                Album.provider == active,
            )
            .order_by(Album.release_date.desc())
        )
        .unique()
        .all()
    )
    return [_album_out(a) for a in albums]


class BulkIds(BaseModel):
    album_ids: list[int]


@router.post("/wanted/download-all")
def download_all_wanted(db: Session = Depends(get_db)):
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
def bulk_download(payload: BulkIds, db: Session = Depends(get_db)):
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


@router.get("/{album_id}", response_model=AlbumOut)
def get_album(album_id: int, db: Session = Depends(get_db)):
    album = db.scalar(
        select(Album).options(joinedload(Album.tracks)).where(Album.id == album_id)
    )
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")
    return _album_out(album)


@router.patch("/{album_id}", response_model=AlbumOut)
def patch_album(album_id: int, payload: AlbumPatch, db: Session = Depends(get_db)):
    album = db.scalar(
        select(Album).options(joinedload(Album.tracks)).where(Album.id == album_id)
    )
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(album, key, value)
    db.commit()
    db.refresh(album)
    return _album_out(album)


@router.post("/{album_id}/download")
def download_album(album_id: int, db: Session = Depends(get_db)):
    album = db.get(Album, album_id)
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")
    if album.status == "skipped":
        album.status = "wanted"
        album.monitored = True
        db.commit()
    job = download_queue.enqueue_album(db, album_id)
    return {"queued": bool(job), "job_id": job.id if job else None}
