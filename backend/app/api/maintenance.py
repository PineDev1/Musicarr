from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Track
from app.models.schemas import MaintenanceResolveRequest, MaintenanceScanOut
from app.services import dedupe
from app.services.history import add_history
from app.services.settings_service import library_root

router = APIRouter(prefix="/maintenance", tags=["maintenance"])


@router.get("/duplicates", response_model=MaintenanceScanOut)
def get_duplicates(db: Session = Depends(get_db)):
    return dedupe.scan(db)


@router.post("/resolve")
def resolve(payload: MaintenanceResolveRequest, db: Session = Depends(get_db)):
    actions = [
        payload.unlink_track_id is not None,
        payload.delete_file_path is not None,
        bool(payload.delete_track_ids),
    ]
    if sum(actions) != 1:
        raise HTTPException(
            status_code=400,
            detail="Provide exactly one of unlink_track_id, delete_file_path, or "
            "keep_track_id/delete_track_ids",
        )

    if payload.unlink_track_id is not None:
        track = db.get(Track, payload.unlink_track_id)
        if not track:
            raise HTTPException(status_code=404, detail="Track not found")
        track.path = None
        db.commit()
        add_history(db, "maintenance", f"Cleared missing file link for '{track.title}'")
        return {"ok": True}

    if payload.delete_file_path is not None:
        root = library_root(db)
        target = Path(payload.delete_file_path).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            raise HTTPException(status_code=400, detail="Path is outside the library folder")
        if target.exists() and target.is_file():
            target.unlink(missing_ok=True)
        add_history(db, "maintenance", f"Deleted orphan file {target}")
        return {"ok": True}

    if payload.delete_track_ids:
        if payload.keep_track_id in payload.delete_track_ids:
            raise HTTPException(status_code=400, detail="keep_track_id can't also be deleted")
        removed = []
        for tid in payload.delete_track_ids:
            track = db.get(Track, tid)
            if not track:
                continue
            if track.path:
                p = Path(track.path)
                if p.exists() and p.is_file():
                    p.unlink(missing_ok=True)
            removed.append(track.title)
            db.delete(track)
        db.commit()
        if removed:
            add_history(db, "maintenance", f"Removed {len(removed)} duplicate track(s)")
        return {"ok": True, "removed": len(removed)}

    raise HTTPException(status_code=400, detail="No action provided")
