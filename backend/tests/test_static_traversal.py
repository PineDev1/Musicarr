from __future__ import annotations

from types import SimpleNamespace

from app import main


def _call(full_path):
    return main.spa_fallback(full_path, SimpleNamespace(method="GET"))


def test_spa_fallback_cannot_read_files_outside_static_dir(tmp_path, monkeypatch):
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<html>app</html>")
    (static / "logo.svg").write_text("<svg/>")
    (tmp_path / "musicarr.db").write_text("SECRET")
    monkeypatch.setattr(main, "STATIC_DIR", static)

    assert _call("logo.svg").path == static / "logo.svg"  # real static files still work
    for evil in ("../musicarr.db", "sub/../../musicarr.db", "..%2fmusicarr.db", str(tmp_path / "musicarr.db")):
        resp = _call(evil)
        assert resp.path == static / "index.html", evil  # falls back to the SPA shell


def test_responses_carry_security_headers_and_big_json_is_gzipped():
    from fastapi.testclient import TestClient

    client = TestClient(main.app)
    r = client.get("/openapi.json", headers={"Accept-Encoding": "gzip"})
    assert r.status_code == 200
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "SAMEORIGIN"
    assert r.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert r.headers.get("content-encoding") == "gzip"
    plain = client.get("/openapi.json", headers={"Accept-Encoding": "identity"})
    assert "content-encoding" not in plain.headers
