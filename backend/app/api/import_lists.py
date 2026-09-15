from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import ImportList
from app.models.schemas import (
    ImportListCreate,
    ImportListOut,
    ImportListRunResult,
    ImportListUpdate,
)
from app.services.import_lists import run_import_list

router = APIRouter(prefix="/import-lists", tags=["import-lists"])


def _out(row: ImportList) -> ImportListOut:
    return ImportListOut(
        id=row.id,
        name=row.name,
        names_raw=row.names_raw,
        interval_minutes=row.interval_minutes,
        enabled=row.enabled,
        last_run_at=row.last_run_at,
        last_result=row.last_result,
        created_at=row.created_at,
    )


def _get_or_404(db: Session, list_id: int) -> ImportList:
    row = db.get(ImportList, list_id)
    if not row:
        raise HTTPException(status_code=404, detail="Import list not found")
    return row


@router.get("", response_model=list[ImportListOut])
def list_import_lists(db: Session = Depends(get_db)):
    rows = db.scalars(select(ImportList).order_by(ImportList.name)).all()
    return [_out(r) for r in rows]


@router.post("", response_model=ImportListOut)
def create_import_list(payload: ImportListCreate, db: Session = Depends(get_db)):
    row = ImportList(
        name=payload.name.strip() or "Untitled list",
        names_raw=payload.names_raw,
        interval_minutes=payload.interval_minutes,
        enabled=payload.enabled,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _out(row)


@router.put("/{list_id}", response_model=ImportListOut)
def update_import_list(list_id: int, payload: ImportListUpdate, db: Session = Depends(get_db)):
    row = _get_or_404(db, list_id)
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return _out(row)


@router.delete("/{list_id}", status_code=204)
def delete_import_list(list_id: int, db: Session = Depends(get_db)):
    row = _get_or_404(db, list_id)
    db.delete(row)
    db.commit()


@router.post("/{list_id}/run", response_model=ImportListRunResult)
def run_import_list_now(list_id: int, db: Session = Depends(get_db)):
    row = _get_or_404(db, list_id)
    result = run_import_list(db, row)
    return ImportListRunResult(**result)
