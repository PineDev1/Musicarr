from __future__ import annotations

from unittest.mock import patch

from app.models import AppSettings
from app.services import maintenance_scheduler


def _settings(db, **overrides) -> AppSettings:
    row = AppSettings(id=1, backup_retention_count=3, **overrides)
    db.add(row)
    db.commit()
    return row


def test_run_backup_job_writes_file_and_prunes(db, tmp_path, monkeypatch):
    _settings(db)
    monkeypatch.setattr(maintenance_scheduler.app_config, "data_dir", tmp_path)
    monkeypatch.setattr(maintenance_scheduler, "SessionLocal", lambda: db)
    db.close = lambda: None  # keep the test session open across the "finally: db.close()"

    for i in range(5):
        with patch(
            "app.services.maintenance_scheduler.export_backup",
            return_value=(b"zip-bytes", f"musicarr-backup-2026010{i}-000000.zip"),
        ):
            maintenance_scheduler.run_backup_job()

    out_dir = tmp_path / "backups"
    files = sorted(out_dir.glob("musicarr-backup-*.zip"))
    assert len(files) == 3


def test_run_dedupe_scan_job_notifies_when_items_found(db, monkeypatch):
    _settings(db, notify_webhook_url="https://example.com/hook", notify_on_maintenance=True)
    monkeypatch.setattr(maintenance_scheduler, "SessionLocal", lambda: db)
    db.close = lambda: None

    with (
        patch(
            "app.services.maintenance_scheduler.dedupe.scan",
            return_value={
                "orphan_db_tracks": [{"track_id": 1}],
                "orphan_files": [],
                "duplicate_groups": [],
            },
        ),
        patch("app.services.maintenance_scheduler.send_notification") as notify,
    ):
        result = maintenance_scheduler.run_dedupe_scan_job()

    assert result["orphan_db_tracks"] == 1
    notify.assert_called_once()
    assert notify.call_args.kwargs["kind"] == "maintenance"


def test_run_dedupe_scan_job_silent_when_clean(db, monkeypatch):
    _settings(db)
    monkeypatch.setattr(maintenance_scheduler, "SessionLocal", lambda: db)
    db.close = lambda: None

    with (
        patch(
            "app.services.maintenance_scheduler.dedupe.scan",
            return_value={"orphan_db_tracks": [], "orphan_files": [], "duplicate_groups": []},
        ),
        patch("app.services.maintenance_scheduler.send_notification") as notify,
    ):
        maintenance_scheduler.run_dedupe_scan_job()

    notify.assert_not_called()


def test_health_check_notifies_once_on_disk_transition(db, monkeypatch, tmp_path):
    _settings(db, library_path=str(tmp_path), low_disk_threshold_gb=999999)
    monkeypatch.setattr(maintenance_scheduler, "SessionLocal", lambda: db)
    db.close = lambda: None
    maintenance_scheduler._last_disk_ok = True
    maintenance_scheduler._last_provider_ok = {}

    class FakeUsage:
        free = 1024

    with (
        patch("app.services.maintenance_scheduler.shutil.disk_usage", return_value=FakeUsage()),
        patch("app.services.maintenance_scheduler.get_provider") as get_provider,
        patch("app.services.maintenance_scheduler.send_notification") as notify,
    ):
        get_provider.return_value.validate_session.return_value = (True, None)
        maintenance_scheduler.run_health_check_job()
        # Second tick with the same low-disk state must not notify again.
        maintenance_scheduler.run_health_check_job()

    disk_calls = [c for c in notify.call_args_list if "disk space" in c.args[1].lower()]
    assert len(disk_calls) == 1
