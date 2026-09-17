from __future__ import annotations

from unittest.mock import patch

from app.api.settings import health
from app.models import AppSettings
from app.services.settings_service import settings_to_out_validated


def _settings(db, **kwargs) -> AppSettings:
    row = AppSettings(id=1, library_path=str(kwargs.pop("library_path", "/tmp")), **kwargs)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_settings_to_out_validated_skips_provider_checks_when_disabled(db):
    row = _settings(db, streaming_enabled=False)
    with patch("app.services.providers.get_provider") as get_provider:
        out = settings_to_out_validated(db, row)
    get_provider.assert_not_called()
    assert out.provider_ok is None
    assert out.provider_error is None
    assert out.deezer_ok is None
    assert out.tidal_ok is None
    assert out.qobuz_ok is None


def test_settings_to_out_validated_checks_providers_when_enabled(db):
    row = _settings(db, streaming_enabled=True, active_provider="deezer")
    fake_provider = type("P", (), {"validate_session": lambda self: (False, "not logged in")})()
    with patch("app.services.providers.get_provider", return_value=fake_provider):
        out = settings_to_out_validated(db, row)
    assert out.provider_ok is False
    assert out.provider_error == "not logged in"


def test_health_endpoint_skips_provider_checks_when_streaming_disabled(db, tmp_path):
    row = _settings(db, streaming_enabled=False, library_path=str(tmp_path))
    with patch("app.api.settings.get_provider") as get_provider:
        out = health(db=db)
    get_provider.assert_not_called()
    assert out.provider_ok is True
    assert out.provider_error is None
    assert out.deezer_ok is True
    assert out.tidal_ok is True
    assert out.qobuz_ok is True
    assert out.streaming_enabled is False


def test_health_endpoint_checks_providers_when_streaming_enabled(db, tmp_path):
    row = _settings(db, streaming_enabled=True, library_path=str(tmp_path), active_provider="qobuz")
    fake_provider = type("P", (), {"validate_session": lambda self: (True, None)})()
    with patch("app.api.settings.get_provider", return_value=fake_provider):
        out = health(db=db)
    assert out.provider_ok is True
    assert out.streaming_enabled is True
