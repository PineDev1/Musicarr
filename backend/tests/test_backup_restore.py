from __future__ import annotations

import json
import sqlite3
import time
import zipfile
from io import BytesIO

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.services import backup_service
from app.services.settings_service import ensure_settings


@pytest.fixture()
def file_db_session(tmp_path, monkeypatch):
    """A real on-disk SQLite DB (export/restore need actual files, not
    the in-memory fixture used by most other tests)."""
    db_path = tmp_path / "musicarr.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    monkeypatch.setattr(backup_service.app_config, "data_dir", tmp_path)
    monkeypatch.setattr(
        backup_service._store, "_persist_path", tmp_path / "last_restore_job.json"
    )

    yield session
    session.close()
    engine.dispose()


SECRET_VALUE = "super-secret-arl-cookie-value"


def test_export_backup_excludes_secrets(file_db_session):
    row = ensure_settings(file_db_session)
    row.arl = SECRET_VALUE
    row.library_path = "/music"
    file_db_session.commit()

    data, filename = backup_service.export_backup(file_db_session)
    assert filename.startswith("musicarr-backup-")
    assert SECRET_VALUE.encode() not in data

    zf = zipfile.ZipFile(BytesIO(data))
    names = set(zf.namelist())
    assert {"manifest.json", "settings.json", "musicarr.db"}.issubset(names)

    settings_json = json.loads(zf.read("settings.json"))
    assert "arl" not in settings_json
    assert settings_json["library_path"] == "/music"

    # The bundled DB snapshot must also have the secret blanked, not just
    # the settings.json sidecar.
    db_bytes = zf.read("musicarr.db")
    assert SECRET_VALUE.encode() not in db_bytes


def test_restore_round_trips_settings_without_touching_secrets(file_db_session, tmp_path):
    row = ensure_settings(file_db_session)
    row.arl = SECRET_VALUE
    row.library_path = "/music/original"
    row.bitrate = "flac"
    file_db_session.commit()

    data, _ = backup_service.export_backup(file_db_session)

    # Change settings after the export, to prove restore actually overwrites them.
    row.library_path = "/music/changed"
    row.bitrate = "320"
    file_db_session.commit()

    job = backup_service.start_restore(data)
    assert job.state == "running"

    deadline = time.time() + 5
    while backup_service.get_restore_job().state == "running" and time.time() < deadline:
        time.sleep(0.02)

    final = backup_service.get_restore_job()
    assert final.state == "done", final.error

    live_db_path = tmp_path / "musicarr.db"
    con = sqlite3.connect(str(live_db_path))
    try:
        cur = con.execute("SELECT library_path, bitrate, arl FROM app_settings WHERE id = 1")
        library_path, bitrate, arl = cur.fetchone()
    finally:
        con.close()

    assert library_path == "/music/original"
    assert bitrate == "flac"
    # Restore must never write real credentials back in (the backup never had any).
    assert arl == ""


def test_restore_rejects_corrupt_archive(file_db_session, tmp_path):
    job = backup_service.start_restore(b"not a zip file")
    deadline = time.time() + 5
    while backup_service.get_restore_job().state == "running" and time.time() < deadline:
        time.sleep(0.02)
    final = backup_service.get_restore_job()
    assert final.state == "error"
    assert "valid backup archive" in final.error
