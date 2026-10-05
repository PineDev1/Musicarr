from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api import backup as backup_api
from app.services import backup_service
from app.services.settings_service import ensure_settings


@pytest.fixture()
def bdir(tmp_path, monkeypatch):
    monkeypatch.setattr(backup_service.app_config, "data_dir", tmp_path)
    return tmp_path / "backups"


def _make(bdir, stamp):
    bdir.mkdir(exist_ok=True)
    (bdir / f"musicarr-backup-{stamp}.zip").write_bytes(b"PK" + stamp.encode())


def test_list_is_newest_first_and_only_matches_backup_names(bdir):
    _make(bdir, "20260101-000000")
    _make(bdir, "20260301-000000")
    (bdir / "notes.txt").write_text("x")
    names = [f["name"] for f in backup_api.list_saved_backups()["files"]]
    assert names == ["musicarr-backup-20260301-000000.zip", "musicarr-backup-20260101-000000.zip"]


@pytest.mark.parametrize("bad", ["../musicarr.db", "..%2fx.zip", "musicarr-backup-1.zip", "a/b.zip", "/etc/passwd"])
def test_names_outside_the_pattern_are_rejected_before_touching_disk(bdir, bad):
    with pytest.raises(HTTPException) as e:
        backup_api.download_saved_backup(bad)
    assert e.value.status_code == 400


def test_missing_backup_is_404_and_delete_removes_it(bdir, db):
    with pytest.raises(HTTPException) as e:
        backup_api.download_saved_backup("musicarr-backup-20260101-000000.zip")
    assert e.value.status_code == 404
    _make(bdir, "20260101-000000")
    backup_api.delete_saved_backup("musicarr-backup-20260101-000000.zip", db)
    assert backup_service.list_backup_files() == []


def test_prune_keeps_only_the_newest_n(bdir):
    for d in ("20260101", "20260102", "20260103", "20260104"):
        _make(bdir, f"{d}-000000")
    assert backup_service.prune_backup_files(2) == 2
    assert [f["name"][-19:-4] for f in backup_service.list_backup_files()] == ["20260104-000000", "20260103-000000"]


def test_restore_from_saved_file_starts_the_restore_job(bdir, db, monkeypatch):
    _make(bdir, "20260101-000000")
    seen = {}
    monkeypatch.setattr(backup_service, "start_restore", lambda data: seen.setdefault("data", data) and backup_service.get_restore_job())
    out = backup_api.restore_saved_backup("musicarr-backup-20260101-000000.zip", db)
    assert seen["data"].startswith(b"PK") and "state" in out
