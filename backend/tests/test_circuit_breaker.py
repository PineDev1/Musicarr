from __future__ import annotations

import httpx

from app.services import musicbrainz


def _reset():
    musicbrainz._consecutive_failures = 0
    musicbrainz._circuit_opened_at = 0.0


def test_circuit_opens_after_repeated_failures(monkeypatch):
    _reset()
    monkeypatch.setattr(musicbrainz, "_throttle", lambda: None)

    class FailingClient:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, *a, **kw):
            raise httpx.ConnectError("boom")

    monkeypatch.setattr(musicbrainz.httpx, "Client", lambda **kw: FailingClient())
    monkeypatch.setattr(musicbrainz.time, "sleep", lambda *_: None)

    for _ in range(musicbrainz._CIRCUIT_OPEN_AFTER):
        musicbrainz._get("/artist/x")

    assert musicbrainz._consecutive_failures >= musicbrainz._CIRCUIT_OPEN_AFTER
    result = musicbrainz._get("/artist/x")
    assert result.get("_status") == 503
    _reset()


def test_circuit_half_opens_after_cooldown_and_recovers_on_success(monkeypatch):
    """Regression: once the circuit trips, it must not stay dead forever —
    after the cooldown window, one trial request gets through, and a
    success there fully resets the breaker."""
    _reset()
    musicbrainz._consecutive_failures = musicbrainz._CIRCUIT_OPEN_AFTER
    musicbrainz._circuit_opened_at = 0.0  # "opened" long ago -> cooldown elapsed

    class OkResponse:
        status_code = 200

        def json(self):
            return {"ok": True}

    class OkClient:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, *a, **kw):
            return OkResponse()

    monkeypatch.setattr(musicbrainz, "_throttle", lambda: None)
    monkeypatch.setattr(musicbrainz.httpx, "Client", lambda **kw: OkClient())

    result = musicbrainz._get("/artist/x")
    assert result == {"ok": True}
    assert musicbrainz._consecutive_failures == 0
    _reset()


def test_circuit_stays_open_within_cooldown_window(monkeypatch):
    _reset()
    musicbrainz._consecutive_failures = musicbrainz._CIRCUIT_OPEN_AFTER
    musicbrainz._circuit_opened_at = musicbrainz.time.monotonic()  # just tripped

    def fail_if_called(**kw):
        raise AssertionError("should not make a request while circuit is open")

    monkeypatch.setattr(musicbrainz.httpx, "Client", fail_if_called)

    result = musicbrainz._get("/artist/x")
    assert result.get("_status") == 503
    _reset()
