from __future__ import annotations

from app.main import app


def test_queue_sse_route_exists():
    paths = set(app.openapi().get("paths", {}))
    assert "/api/events/queue" in paths


def test_queue_ws_route_removed():
    paths = set(app.openapi().get("paths", {}))
    assert "/api/ws/queue" not in paths
    assert not any("ws/queue" in p for p in paths)


def test_queue_snapshot_returns_list():
    from app.api.events import _queue_snapshot

    snap = _queue_snapshot()
    assert isinstance(snap, list)
