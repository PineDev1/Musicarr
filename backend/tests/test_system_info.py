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
