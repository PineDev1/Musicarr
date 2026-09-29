from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import HistoryEvent


def add_history(db: Session, event_type: str, message: str) -> HistoryEvent:
    event = HistoryEvent(event_type=event_type, message=message)
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def audit(db: Session, action: str, detail: str = "", *, actor: str = "") -> HistoryEvent:
    """Record an admin/security-relevant action. Never pass secret values in detail."""
    who = f" by {actor}" if actor else ""
    return add_history(db, "audit", f"{action}{who}" + (f": {detail}" if detail else ""))
