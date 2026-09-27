"""The /health endpoint must report the *resolved* acquisition mode, not
just the raw streaming_enabled/preferred_download_method fields — the two
can disagree (streaming_enabled=False overrides any stored
preferred_download_method), and nothing in the UI reconciled that for the
user before this."""
from __future__ import annotations

from unittest.mock import patch

from app.api.settings import health
from app.models import AppSettings
from tests.conftest import _artist  # noqa: F401 — ensures models are registered


def _settings(db, **kwargs) -> AppSettings:
    row = AppSettings(id=1, library_path="/tmp", active_provider="deezer", **kwargs)
    db.add(row)
    db.commit()
    return row


def _no_provider_checks():
    return patch(
        "app.api.settings.get_provider",
        return_value=type("P", (), {"validate_session": lambda self: (True, None)})(),
    )


def test_health_reports_streaming_mode(db):
    _settings(db, streaming_enabled=True, preferred_download_method="streaming")
    with _no_provider_checks():
        out = health(db=db)
    assert out.resolved_acquisition_mode == "streaming"


def test_health_reports_indexer_mode_when_streaming_disabled(db):
    _settings(db, streaming_enabled=False, preferred_download_method="streaming")
    with _no_provider_checks():
        out = health(db=db)
    # streaming_enabled=False must override the stored preference, exactly
    # like resolve_download_method does for real downloads — the health
    # endpoint must not report a mode that download_queue would never honor.
    assert out.resolved_acquisition_mode == "indexer"


def test_health_reports_streaming_then_indexer_mode(db):
    _settings(db, streaming_enabled=True, preferred_download_method="streaming_then_indexer")
    with _no_provider_checks():
        out = health(db=db)
    assert out.resolved_acquisition_mode == "streaming_then_indexer"
