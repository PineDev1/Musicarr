from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services import trash
from app.services.server_tools import iso_utc
from app.services.history import add_history, audit

router = APIRouter(prefix="/trash", tags=["trash"])


def _out(item) -> dict:
    return {
        "id": item.id,
        "label": item.label,
        "reason": item.reason,
        "original_path": item.original_path,
        "is_dir": bool(item.is_dir),
        "size_bytes": item.size_bytes or 0,
        "deleted_at": iso_utc(item.deleted_at),
    }


@router.get("")
def list_trash(db: Session = Depends(get_db)):
    items = trash.list_items(db)
    return {
        "retention_days": trash.retention_days(db),
        "total_bytes": sum(i.size_bytes or 0 for i in items),
        "items": [_out(i) for i in items],
    }


@router.post("/{item_id}/restore")
def restore_item(item_id: int, db: Session = Depends(get_db)):
    try:
        item = trash.restore(db, item_id)
    except trash.TrashError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    add_history(db, "maintenance", f"Restored '{item.label}' from the trash")
    return {"ok": True, "restored_to": item.original_path}


@router.delete("/{item_id}")
def delete_item(item_id: int, db: Session = Depends(get_db)):
    try:
        trash.purge(db, item_id)
    except trash.TrashError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    audit(db, "Trash item deleted permanently", f"id {item_id}")
    return {"ok": True}


@router.delete("")
def empty_trash(db: Session = Depends(get_db)):
    removed = trash.empty(db)
    audit(db, "Trash emptied", f"{removed} item(s)")
    return {"ok": True, "removed": removed}
