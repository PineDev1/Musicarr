from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.player import _current_player_user, _downloaded_tracks_query, _track_out
from app.core.database import get_db
from app.models import PlayerQueueState, Track
from app.models.schemas import PlayerTrackOut

router = APIRouter(prefix="/player/me/queue", tags=["player-queue"])

MAX_QUEUE = 500


class QueueSave(BaseModel):
    track_ids: list[int] = Field(default_factory=list, max_length=MAX_QUEUE)
    index: int = 0
    position: float = 0.0
    shuffle: bool = False
    repeat: str = "off"
    source_label: str = Field(default="", max_length=120)
    device_id: str = Field(min_length=1, max_length=64)
    device_name: str = Field(default="", max_length=80)


class QueueOut(BaseModel):
    exists: bool = False
    tracks: list[PlayerTrackOut] = []
    index: int = 0
    position: float = 0.0
    shuffle: bool = False
    repeat: str = "off"
    source_label: str = ""
    device_id: str = ""
    device_name: str = ""
    updated_at: datetime | None = None


@router.put("")
def save_queue(payload: QueueSave, request: Request, db: Session = Depends(get_db)):
    user = _current_player_user(request, db)
    if not payload.track_ids:
        # An emptied queue clears the saved one so it doesn't resurrect on another device.
        row = db.scalar(select(PlayerQueueState).where(PlayerQueueState.user_id == user.id))
        if row:
            db.delete(row)
            db.commit()
        return {"ok": True, "saved": False}
    row = db.scalar(select(PlayerQueueState).where(PlayerQueueState.user_id == user.id))
    if row is None:
        row = PlayerQueueState(user_id=user.id)
        db.add(row)
    row.track_ids_json = json.dumps(payload.track_ids)
    row.index = max(0, min(payload.index, len(payload.track_ids) - 1))
    row.position = max(0.0, float(payload.position or 0.0))
    row.shuffle = bool(payload.shuffle)
    row.repeat = payload.repeat if payload.repeat in ("off", "all", "one") else "off"
    row.source_label = payload.source_label
    row.device_id = payload.device_id
    row.device_name = payload.device_name
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True, "saved": True}


@router.get("", response_model=QueueOut)
def get_queue(request: Request, db: Session = Depends(get_db)):
    user = _current_player_user(request, db)
    row = db.scalar(select(PlayerQueueState).where(PlayerQueueState.user_id == user.id))
    if row is None:
        return QueueOut()
    try:
        ids = [int(i) for i in json.loads(row.track_ids_json or "[]")]
    except (ValueError, TypeError):
        ids = []
    by_id = {
        t.id: t
        for t in db.scalars(
            _downloaded_tracks_query().where(Track.id.in_(ids or [-1]))
        ).unique()
    }
    wanted_id = ids[row.index] if 0 <= row.index < len(ids) else None
    playable = [i for i in ids if i in by_id]
    if not playable:
        return QueueOut()
    # Tracks deleted or no longer on disk drop out; keep pointing at the same
    # song when we can, otherwise at the nearest surviving position.
    if wanted_id in by_id:
        index, position = playable.index(wanted_id), row.position
    else:
        index, position = min(row.index, len(playable) - 1), 0.0
    return QueueOut(
        exists=True,
        tracks=[_track_out(by_id[i]) for i in playable],
        index=index,
        position=position,
        shuffle=row.shuffle,
        repeat=row.repeat,
        source_label=row.source_label,
        device_id=row.device_id,
        device_name=row.device_name,
        updated_at=row.updated_at,
    )
