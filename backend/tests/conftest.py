from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models import Album, Artist, HistoryEvent, Track  # noqa: F401 — register tables


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _artist(db, *, name: str, provider: str, provider_id: str, link_group_id: str | None = None):
    row = Artist(
        provider=provider,
        provider_id=provider_id,
        deezer_id=abs(hash(f"{provider}:{provider_id}")) % 1_000_000,
        name=name,
        image_url=None,
        monitored=True,
        link_group_id=link_group_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
