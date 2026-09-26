from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.schemas import PushSubscriptionIn
from app.services import push as push_service

router = APIRouter(prefix="/push", tags=["push"])


@router.get("/vapid-public-key")
def vapid_public_key(db: Session = Depends(get_db)):
    pub, _ = push_service.ensure_vapid_keys(db)
    return {"public_key": pub}


@router.post("/subscribe")
def subscribe(payload: PushSubscriptionIn, db: Session = Depends(get_db)):
    push_service.add_subscription(
        db, endpoint=payload.endpoint, p256dh=payload.p256dh, auth=payload.auth
    )
    return {"ok": True}


@router.post("/unsubscribe")
def unsubscribe(payload: PushSubscriptionIn, db: Session = Depends(get_db)):
    push_service.remove_subscription(db, payload.endpoint)
    return {"ok": True}


@router.post("/test")
def send_test(db: Session = Depends(get_db)):
    sent = push_service.send_push(db, "Musicarr test", "Push notifications are working.")
    return {"sent": sent}
