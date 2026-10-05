from __future__ import annotations

import sqlite3

from app.services.backup_service import _snapshot_db_bytes


def _make_db(path, *, with_player_secrets=True):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE app_settings (id INTEGER, " + ", ".join(
        f"{c} TEXT" for c in (
            "arl", "tidal_access_token", "tidal_refresh_token", "tidal_expiry", "qobuz_email",
            "qobuz_user_id", "qobuz_user_auth_token", "qobuz_app_id", "qobuz_app_secret",
            "notify_token", "media_refresh_token", "auth_password_hash", "auth_secret",
        )
    ) + ")")
    con.execute("INSERT INTO app_settings (id, arl) VALUES (1, 'SECRET_ARL')")
    if with_player_secrets:
        con.execute(
            "CREATE TABLE player_users (id INTEGER, username TEXT, subsonic_secret TEXT, "
            "lastfm_session_key TEXT, lastfm_pending_token TEXT)"
        )
        con.execute("INSERT INTO player_users VALUES (1, 'riley', 'subsecret', 'lfmkey', 'lfmtok')")
    con.commit()
    con.close()


def _read(data: bytes, tmp_path):
    out = tmp_path / "snap.sqlite"
    out.write_bytes(data)
    return sqlite3.connect(out)


def test_backup_blanks_player_credentials_but_keeps_accounts(tmp_path):
    src = tmp_path / "live.db"
    _make_db(src)
    con = _read(_snapshot_db_bytes(src), tmp_path)
    assert con.execute("SELECT arl FROM app_settings").fetchone()[0] == ""
    row = con.execute(
        "SELECT username, subsonic_secret, lastfm_session_key, lastfm_pending_token FROM player_users"
    ).fetchone()
    assert row == ("riley", None, None, None)
    con.close()


def test_backup_tolerates_snapshot_without_player_secret_columns(tmp_path):
    src = tmp_path / "old.db"
    _make_db(src, with_player_secrets=False)
    con = _read(_snapshot_db_bytes(src), tmp_path)
    assert con.execute("SELECT arl FROM app_settings").fetchone()[0] == ""
    con.close()


def test_backup_strips_totp_secrets_and_cast_tokens(tmp_path):
    src = tmp_path / "live.db"
    _make_db(src)
    con = sqlite3.connect(src)
    con.execute("CREATE TABLE admin_users (id INTEGER, username TEXT, totp_secret TEXT, totp_enabled INTEGER)")
    con.execute("INSERT INTO admin_users VALUES (1, 'riley', 'JBSWY3DPEHPK3PXP', 1)")
    con.execute("CREATE TABLE player_cast_tokens (id INTEGER, token TEXT)")
    con.execute("INSERT INTO player_cast_tokens VALUES (1, 'bearer-secret')")
    con.commit()
    con.close()
    out = _read(_snapshot_db_bytes(src), tmp_path)
    # 2FA is switched off together with the secret, so the account isn't locked out.
    assert out.execute("SELECT username, totp_secret, totp_enabled FROM admin_users").fetchone() == ("riley", None, 0)
    assert out.execute("SELECT COUNT(*) FROM player_cast_tokens").fetchone()[0] == 0
    out.close()
