from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AdminUser
from app.models.schemas import AdminUserOut
from app.services.app_auth import hash_password, verify_password


def admin_user_out(user: AdminUser) -> AdminUserOut:
    return AdminUserOut(
        id=user.id,
        username=user.username,
        display_name=user.display_name or "",
        is_active=bool(user.is_active),
        created_at=user.created_at,
    )


def list_users(db: Session) -> list[AdminUser]:
    return list(db.scalars(select(AdminUser).order_by(AdminUser.username)).all())


def create_user(db: Session, *, username: str, password: str, display_name: str = "") -> AdminUser:
    name = username.strip()
    if not name:
        raise ValueError("Username required")
    existing = db.scalar(select(AdminUser).where(AdminUser.username == name))
    if existing:
        raise ValueError("Username already exists")
    user = AdminUser(
        username=name,
        password_hash=hash_password(password),
        display_name=(display_name or name).strip(),
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def update_user(
    db: Session,
    user_id: int,
    *,
    password: str | None = None,
    display_name: str | None = None,
    is_active: bool | None = None,
) -> AdminUser:
    user = db.get(AdminUser, user_id)
    if not user:
        raise ValueError("User not found")
    if password is not None and password.strip():
        user.password_hash = hash_password(password.strip())
    if display_name is not None:
        user.display_name = display_name.strip()
    if is_active is not None:
        user.is_active = is_active
    db.commit()
    db.refresh(user)
    return user


def delete_user(db: Session, user_id: int) -> None:
    user = db.get(AdminUser, user_id)
    if not user:
        raise ValueError("User not found")
    db.delete(user)
    db.commit()


def authenticate(db: Session, username: str, password: str) -> AdminUser | None:
    name = (username or "").strip()
    if not name:
        return None
    user = db.scalar(select(AdminUser).where(AdminUser.username == name))
    if not user or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user
