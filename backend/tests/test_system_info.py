from __future__ import annotations

import logging

from app.services import system_info
from app.services.system_info import RingBufferHandler, redact


def test_redact_strips_secrets_in_common_shapes():
    assert "abc123secret" not in redact("GET /x?apikey=abc123secret&t=music")
    assert "abc123secret" not in redact("login arl=abc123secret ok")
    assert "abc123secret" not in redact('{"password": "abc123secret"}')
    assert "abc123secretvalue" not in redact("Authorization: Bearer abc123secretvalue")
    assert "AAAAAAAAAAAAAAAAAAAA" not in redact("GET /api/player/cast/AAAAAAAAAAAAAAAAAAAA/stream/1")
    line = 'GET /rest/ping?u=riley&t=0123456789abcdef0123456789abcdef&s=saltvalue&v=1.16.1 HTTP/1.1'
    out = redact(line)
    assert "0123456789abcdef" not in out and "saltvalue" not in out and "u=riley" in out
    assert "p=hunter2" not in redact("GET /rest/ping?u=riley&p=hunter2&f=json")
    assert redact("plain message, nothing secret") == "plain message, nothing secret"


def test_ring_buffer_caps_filters_and_redacts():
    h = RingBufferHandler(capacity=3)
    log = logging.getLogger("t.ring")
    log.setLevel(logging.DEBUG)
    log.addHandler(h)
    try:
        for i in range(5):
            log.info("event %d", i)
        log.error("failed token=SECRETVALUE")
        rows = h.snapshot()
        assert len(rows) == 3
        assert rows[0]["message"] == "failed token=***"
        assert [r["message"] for r in h.snapshot(level="ERROR")] == ["failed token=***"]
        assert [r["message"] for r in h.snapshot(search="event 4")] == ["event 4"]
    finally:
        log.removeHandler(h)


def test_system_status_shape(tmp_path):
    out = system_info.system_status(str(tmp_path))
    assert out["disk"]["free"] > 0 and out["uptime_seconds"] >= 0
    assert isinstance(out["tasks"], list)


def test_run_task_now_actually_fires_the_job_and_rejects_unknown_ids(monkeypatch):
    import threading

    from apscheduler.schedulers.background import BackgroundScheduler

    fired = threading.Event()
    sched = BackgroundScheduler()
    sched.start()
    try:
        sched.add_job(fired.set, "interval", hours=6, id="far_future")
        monkeypatch.setattr(system_info, "_running_schedulers", lambda: [sched])
        assert not fired.is_set()  # next natural run is 6h away
        assert system_info.run_task_now("far_future") is True
        assert fired.wait(5), "job never ran after run_task_now"
        assert system_info.run_task_now("does_not_exist") is False
    finally:
        sched.shutdown(wait=False)


def test_prune_history_removes_only_rows_past_retention(db):
    from datetime import datetime, timedelta, timezone

    from app.models import HistoryEvent
    from app.services.maintenance_scheduler import prune_history

    now = datetime.now(timezone.utc)
    db.add_all([
        HistoryEvent(event_type="audit", message="old", created_at=now - timedelta(days=400)),
        HistoryEvent(event_type="downloaded", message="recent", created_at=now - timedelta(days=30)),
    ])
    db.commit()
    assert prune_history(db) == 1
    assert [e.message for e in db.query(HistoryEvent).all()] == ["recent"]
