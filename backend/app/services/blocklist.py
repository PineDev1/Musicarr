from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BlocklistEntry, DownloadJob
from app.services.release_scoring import _norm


def title_key(title: str | None) -> str:
    return _norm(title)[:1000]


def blocked_keys(db: Session) -> set[str]:
    return set(db.scalars(select(BlocklistEntry.title_key)))


def is_blocklisted(db: Session, title: str | None) -> bool:
    key = title_key(title)
    return bool(key) and db.scalar(
        select(BlocklistEntry.id).where(BlocklistEntry.title_key == key).limit(1)
    ) is not None


def add_release(
    db: Session,
    release_title: str,
    *,
    reason: str = "",
    indexer_id: int | None = None,
    artist_name: str = "",
    album_title: str = "",
) -> BlocklistEntry | None:
    key = title_key(release_title)
    if not key:
        return None
    existing = db.scalar(select(BlocklistEntry).where(BlocklistEntry.title_key == key))
    if existing:
        return existing
    row = BlocklistEntry(
        release_title=release_title.strip()[:1024],
        title_key=key,
        indexer_id=indexer_id,
        artist_name=artist_name,
        album_title=album_title,
        reason=reason[:512],
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def add_from_job(db: Session, job: DownloadJob, reason: str) -> BlocklistEntry | None:
    if job.source != "indexer" or not (job.release_title or "").strip():
        return None
    return add_release(
        db,
        job.release_title,
        reason=reason,
        indexer_id=job.indexer_id,
        artist_name=job.artist_name,
        album_title=job.album_title,
    )
