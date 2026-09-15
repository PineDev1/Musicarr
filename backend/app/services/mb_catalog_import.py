from __future__ import annotations

import bz2
import json
import logging
import os
import sqlite3
import tarfile
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from app.services.background_job import BackgroundJobStore, JobState
from app.services.mb_catalog_paths import (
    CORE_DUMP_TABLES,
    DERIVED_DUMP_TABLES,
    DUMP_BASE,
    DUMP_TABLES,
    MAX_CATALOG_BYTES,
    USER_AGENT,
    catalog_db_path,
    catalog_dir,
    catalog_meta_path,
    catalog_work_dir,
)

logger = logging.getLogger("musicarr.mb_catalog")


@dataclass
class CatalogJob(JobState):
    """Adds MusicBrainz-dump-specific fields to the shared job shape."""

    bytes_done: int = 0
    bytes_total: int = 0
    dump_version: str = ""


_store = BackgroundJobStore(
    job_factory=CatalogJob,
    persist_path=catalog_dir() / "last_job.json",
    thread_name="mb-catalog-import",
)


def _set_job(**kwargs: Any) -> None:
    _store.update(**kwargs)


def get_job() -> CatalogJob:
    return _store.get()


def catalog_ready() -> bool:
    path = catalog_db_path()
    return path.is_file() and path.stat().st_size > 0


def read_catalog_meta() -> dict[str, Any]:
    meta_path = catalog_meta_path()
    if not meta_path.is_file():
        return {}
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def write_catalog_meta(data: dict[str, Any]) -> None:
    catalog_meta_path().write_text(json.dumps(data, indent=2), encoding="utf-8")


def fetch_latest_dump_version(timeout: float = 30.0) -> str:
    url = f"{DUMP_BASE}/LATEST"
    with httpx.Client(timeout=timeout, headers={"User-Agent": USER_AGENT}, follow_redirects=True, trust_env=False) as client:
        res = client.get(url)
        res.raise_for_status()
        version = (res.text or "").strip()
    if not version:
        raise RuntimeError("MusicBrainz LATEST dump id was empty")
    return version


def catalog_status(*, mode: str = "local") -> dict[str, Any]:
    path = catalog_db_path()
    meta = read_catalog_meta()
    ready = catalog_ready()
    size = path.stat().st_size if ready else 0
    job = get_job()
    status = "missing"
    if job.state == "running":
        status = "updating"
    elif job.state == "error" and not ready:
        status = "failed"
    elif ready:
        status = "ready"
    elif job.state == "error":
        status = "failed"
    return {
        "status": status,
        "ready": ready,
        "path": str(path.resolve()),
        "size_bytes": size,
        "dump_version": meta.get("dump_version") or "",
        "imported_at": meta.get("imported_at") or "",
        "mode": mode or "local",
        "max_bytes": MAX_CATALOG_BYTES,
        "job": asdict(job),
    }


def start_catalog_update(*, force: bool = False) -> CatalogJob:
    if _store.is_running():
        return get_job()
    try:
        return _store.start(
            target=_run_import_job,
            initial={
                "phase": "downloading",
                "message": "Starting MusicBrainz catalog update…",
            },
        )
    except RuntimeError:
        return get_job()


def _run_import_job() -> None:
    work = catalog_work_dir()
    core_archive = work / "mbdump.tar.bz2"
    derived_archive = work / "mbdump-derived.tar.bz2"
    extract_dir = work / "extract"
    try:
        _set_job(phase="downloading", message="Resolving latest dump version…", progress_pct=1.0)
        version = fetch_latest_dump_version()
        _set_job(dump_version=version, message=f"Latest dump: {version}")

        core_url = f"{DUMP_BASE}/{version}/mbdump.tar.bz2"
        derived_url = f"{DUMP_BASE}/{version}/mbdump-derived.tar.bz2"
        _download_file(
            core_url,
            core_archive,
            progress_start=2.0,
            progress_end=55.0,
            skip_if_complete=True,
        )
        _download_file(
            derived_url,
            derived_archive,
            progress_start=55.0,
            progress_end=70.0,
            skip_if_complete=True,
        )

        if extract_dir.exists():
            for child in extract_dir.rglob("*"):
                if child.is_file():
                    child.unlink(missing_ok=True)
        extract_dir.mkdir(parents=True, exist_ok=True)
        _set_job(phase="extracting", message="Extracting required tables…", progress_pct=71.0)
        found: set[str] = set()
        found |= _extract_tables(
            core_archive,
            extract_dir,
            tables=CORE_DUMP_TABLES,
            progress_start=71.0,
            progress_end=76.0,
        )
        found |= _extract_tables(
            derived_archive,
            extract_dir,
            tables=DERIVED_DUMP_TABLES,
            progress_start=76.0,
            progress_end=79.0,
        )
        wanted = {f"mbdump/{name}" for name in DUMP_TABLES}
        missing = wanted - found
        if missing:
            raise RuntimeError(f"Dump missing required tables: {', '.join(sorted(missing))}")

        _set_job(phase="building", message="Building SQLite catalog…", progress_pct=80.0)
        tmp_db = work / "musicbrainz_catalog.sqlite.tmp"
        if tmp_db.exists():
            tmp_db.unlink()
        _build_sqlite(extract_dir, tmp_db)

        size = tmp_db.stat().st_size
        if size > MAX_CATALOG_BYTES:
            tmp_db.unlink(missing_ok=True)
            raise RuntimeError(
                f"Catalog would be {size / (1024**3):.1f} GiB, exceeding the 20 GiB limit"
            )

        _set_job(phase="finalizing", message="Installing catalog…", progress_pct=96.0)
        final_db = catalog_db_path()
        os.replace(tmp_db, final_db)
        write_catalog_meta(
            {
                "dump_version": version,
                "imported_at": datetime.now(timezone.utc).isoformat(),
                "size_bytes": final_db.stat().st_size,
            }
        )
        try:
            from app.services import musicbrainz as mb

            mb.clear_cache()
            mb.reload_local_store()
        except Exception:  # noqa: BLE001
            logger.exception("Failed to reload MusicBrainz local store after import")

        try:
            core_archive.unlink(missing_ok=True)
            derived_archive.unlink(missing_ok=True)
            for path in extract_dir.rglob("*"):
                if path.is_file():
                    path.unlink(missing_ok=True)
        except OSError:
            pass

        _set_job(
            state="done",
            phase="done",
            progress_pct=100.0,
            message=f"Catalog ready ({final_db.stat().st_size / (1024**3):.2f} GiB)",
            finished_at=datetime.now(timezone.utc).isoformat(),
            error="",
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("MusicBrainz catalog import failed")
        _set_job(
            state="error",
            phase="error",
            message="Catalog import failed",
            error=str(exc),
            finished_at=datetime.now(timezone.utc).isoformat(),
        )


def _remote_content_length(url: str) -> int | None:
    try:
        with httpx.Client(
            timeout=30.0,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
            trust_env=False,
        ) as client:
            res = client.head(url)
            if res.status_code >= 400:
                res = client.get(url, headers={"Range": "bytes=0-0"})
            res.raise_for_status()
            total = int(res.headers.get("Content-Length") or 0)
            cr = res.headers.get("Content-Range") or ""
            if "/" in cr:
                try:
                    total = int(cr.rsplit("/", 1)[-1])
                except ValueError:
                    pass
            return total if total > 0 else None
    except Exception:  # noqa: BLE001
        logger.debug("Could not probe remote size for %s", url, exc_info=True)
        return None


def _download_file(
    url: str,
    dest: Path,
    *,
    progress_start: float,
    progress_end: float,
    skip_if_complete: bool = False,
) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if skip_if_complete and dest.is_file() and dest.stat().st_size > 0:
        remote = _remote_content_length(url)
        local = dest.stat().st_size
        if remote is None or local == remote:
            _set_job(
                progress_pct=progress_end,
                bytes_done=local,
                bytes_total=remote or local,
                message=f"Reusing existing {dest.name} ({_fmt_bytes(local)})",
            )
            logger.info("Skipping download; reusing %s (%s bytes)", dest, local)
            return

    partial = dest.with_suffix(dest.suffix + ".partial")
    headers = {"User-Agent": USER_AGENT}
    with httpx.Client(timeout=None, headers=headers, follow_redirects=True, trust_env=False) as client:
        with client.stream("GET", url) as res:
            res.raise_for_status()
            total = int(res.headers.get("Content-Length") or 0)
            _set_job(bytes_total=total, bytes_done=0, message=f"Downloading {dest.name}…")
            done = 0
            with partial.open("wb") as out:
                for chunk in res.iter_bytes(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    out.write(chunk)
                    done += len(chunk)
                    pct = progress_start
                    if total > 0:
                        pct = progress_start + (progress_end - progress_start) * (done / total)
                    _set_job(
                        bytes_done=done,
                        progress_pct=min(progress_end, pct),
                        message=f"Downloading {dest.name} — {_fmt_bytes(done)}"
                        + (f" / {_fmt_bytes(total)}" if total else ""),
                    )
    os.replace(partial, dest)


def _extract_tables(
    archive_path: Path,
    extract_dir: Path,
    *,
    tables: tuple[str, ...],
    progress_start: float = 71.0,
    progress_end: float = 79.0,
) -> set[str]:
    wanted = {f"mbdump/{name}" for name in tables}
    found: set[str] = set()
    with tarfile.open(archive_path, mode="r:bz2") as tar:
        members = [m for m in tar.getmembers() if m.name in wanted and m.isfile()]
        total = len(members) or 1
        for idx, member in enumerate(members):
            tar.extract(member, path=extract_dir)
            found.add(member.name)
            pct = progress_start + (progress_end - progress_start) * ((idx + 1) / total)
            _set_job(
                progress_pct=pct,
                message=f"Extracted {member.name.split('/')[-1]} ({idx + 1}/{total})",
            )
    return found


def _pg_null(value: str) -> str | None:
    if value == "\\N":
        return None
    return value


def _build_sqlite(extract_dir: Path, db_path: Path) -> None:
    root = extract_dir / "mbdump"
    con = sqlite3.connect(str(db_path))
    try:
        con.execute("PRAGMA journal_mode=OFF")
        con.execute("PRAGMA synchronous=OFF")
        con.execute("PRAGMA temp_store=MEMORY")
        con.executescript(
            """
            CREATE TABLE artist (
              id INTEGER PRIMARY KEY,
              gid TEXT NOT NULL,
              name TEXT NOT NULL
            );
            CREATE TABLE artist_alias (
              artist_id INTEGER NOT NULL,
              name TEXT NOT NULL
            );
            CREATE TABLE artist_credit (
              id INTEGER PRIMARY KEY,
              name TEXT NOT NULL
            );
            CREATE TABLE artist_credit_name (
              artist_credit INTEGER NOT NULL,
              position INTEGER NOT NULL,
              artist_id INTEGER NOT NULL,
              name TEXT NOT NULL,
              join_phrase TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE release_group (
              id INTEGER PRIMARY KEY,
              gid TEXT NOT NULL,
              name TEXT NOT NULL,
              artist_credit INTEGER NOT NULL,
              primary_type_id INTEGER
            );
            CREATE TABLE release_group_meta (
              id INTEGER PRIMARY KEY,
              first_release_year INTEGER
            );
            CREATE TABLE release_group_primary_type (
              id INTEGER PRIMARY KEY,
              name TEXT NOT NULL
            );
            CREATE TABLE release_group_secondary_type (
              id INTEGER PRIMARY KEY,
              name TEXT NOT NULL
            );
            CREATE TABLE release_group_secondary_type_join (
              release_group INTEGER NOT NULL,
              secondary_type INTEGER NOT NULL
            );
            CREATE TABLE artist_rg (
              artist_id INTEGER NOT NULL,
              release_group_id INTEGER NOT NULL
            );
            """
        )

        steps = [
            ("artist", _load_artist),
            ("artist_alias", _load_artist_alias),
            ("artist_credit", _load_artist_credit),
            ("artist_credit_name", _load_artist_credit_name),
            ("release_group", _load_release_group),
            ("release_group_meta", _load_release_group_meta),
            ("release_group_primary_type", _load_primary_type),
            ("release_group_secondary_type", _load_secondary_type),
            ("release_group_secondary_type_join", _load_secondary_join),
        ]
        for idx, (name, loader) in enumerate(steps):
            src = root / name
            if not src.is_file():
                raise RuntimeError(f"Missing extracted table file: {name}")
            _set_job(
                message=f"Loading {name}…",
                progress_pct=80.0 + 12.0 * (idx / max(len(steps), 1)),
            )
            loader(con, src)
            size = db_path.stat().st_size
            if size > MAX_CATALOG_BYTES:
                raise RuntimeError(
                    f"Catalog exceeded 20 GiB while loading {name} ({size / (1024**3):.1f} GiB)"
                )

        _set_job(message="Building artist↔release-group index…", progress_pct=93.0)
        con.execute(
            """
            INSERT INTO artist_rg (artist_id, release_group_id)
            SELECT DISTINCT acn.artist_id, rg.id
            FROM release_group rg
            JOIN artist_credit_name acn ON acn.artist_credit = rg.artist_credit
            """
        )
        _set_job(message="Creating indexes…", progress_pct=95.0)
        con.executescript(
            """
            CREATE UNIQUE INDEX idx_artist_gid ON artist(gid);
            CREATE INDEX idx_artist_name ON artist(name COLLATE NOCASE);
            CREATE INDEX idx_artist_alias_name ON artist_alias(name COLLATE NOCASE);
            CREATE INDEX idx_artist_alias_artist ON artist_alias(artist_id);
            CREATE INDEX idx_acn_credit ON artist_credit_name(artist_credit);
            CREATE INDEX idx_acn_artist ON artist_credit_name(artist_id);
            CREATE UNIQUE INDEX idx_rg_gid ON release_group(gid);
            CREATE INDEX idx_rg_name ON release_group(name COLLATE NOCASE);
            CREATE INDEX idx_rg_credit ON release_group(artist_credit);
            CREATE INDEX idx_artist_rg_artist ON artist_rg(artist_id);
            CREATE INDEX idx_artist_rg_rg ON artist_rg(release_group_id);
            CREATE INDEX idx_sec_join_rg ON release_group_secondary_type_join(release_group);
            """
        )
        con.commit()
    finally:
        con.close()


def _iter_tsv(path: Path):
    with path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
        for line in fh:
            yield line.rstrip("\n").split("\t")


def _batched_insert(con: sqlite3.Connection, sql: str, rows: list[tuple], batch: int = 5000) -> None:
    cur = con.cursor()
    for i in range(0, len(rows), batch):
        cur.executemany(sql, rows[i : i + batch])
    con.commit()


def _load_artist(con: sqlite3.Connection, path: Path) -> None:
    rows: list[tuple] = []
    sql = "INSERT INTO artist(id, gid, name) VALUES (?, ?, ?)"
    for cols in _iter_tsv(path):
        if len(cols) < 3:
            continue
        rows.append((int(cols[0]), cols[1], cols[2]))
        if len(rows) >= 20000:
            _batched_insert(con, sql, rows)
            rows.clear()
    if rows:
        _batched_insert(con, sql, rows)


def _load_artist_alias(con: sqlite3.Connection, path: Path) -> None:
    rows: list[tuple] = []
    sql = "INSERT INTO artist_alias(artist_id, name) VALUES (?, ?)"
    for cols in _iter_tsv(path):
        if len(cols) < 3:
            continue
        rows.append((int(cols[1]), cols[2]))
        if len(rows) >= 20000:
            _batched_insert(con, sql, rows)
            rows.clear()
    if rows:
        _batched_insert(con, sql, rows)


def _load_artist_credit(con: sqlite3.Connection, path: Path) -> None:
    rows: list[tuple] = []
    sql = "INSERT INTO artist_credit(id, name) VALUES (?, ?)"
    for cols in _iter_tsv(path):
        if len(cols) < 2:
            continue
        rows.append((int(cols[0]), cols[1]))
        if len(rows) >= 20000:
            _batched_insert(con, sql, rows)
            rows.clear()
    if rows:
        _batched_insert(con, sql, rows)


def _load_artist_credit_name(con: sqlite3.Connection, path: Path) -> None:
    rows: list[tuple] = []
    sql = (
        "INSERT INTO artist_credit_name(artist_credit, position, artist_id, name, join_phrase) "
        "VALUES (?, ?, ?, ?, ?)"
    )
    for cols in _iter_tsv(path):
        if len(cols) < 5:
            continue
        rows.append((int(cols[0]), int(cols[1]), int(cols[2]), cols[3], cols[4] or ""))
        if len(rows) >= 20000:
            _batched_insert(con, sql, rows)
            rows.clear()
    if rows:
        _batched_insert(con, sql, rows)


def _load_release_group(con: sqlite3.Connection, path: Path) -> None:
    rows: list[tuple] = []
    sql = (
        "INSERT INTO release_group(id, gid, name, artist_credit, primary_type_id) "
        "VALUES (?, ?, ?, ?, ?)"
    )
    for cols in _iter_tsv(path):
        if len(cols) < 5:
            continue
        type_raw = _pg_null(cols[4])
        rows.append(
            (
                int(cols[0]),
                cols[1],
                cols[2],
                int(cols[3]),
                int(type_raw) if type_raw is not None else None,
            )
        )
        if len(rows) >= 20000:
            _batched_insert(con, sql, rows)
            rows.clear()
    if rows:
        _batched_insert(con, sql, rows)


def _load_release_group_meta(con: sqlite3.Connection, path: Path) -> None:
    rows: list[tuple] = []
    sql = "INSERT INTO release_group_meta(id, first_release_year) VALUES (?, ?)"
    for cols in _iter_tsv(path):
        if len(cols) < 3:
            continue
        year_raw = _pg_null(cols[2])
        rows.append((int(cols[0]), int(year_raw) if year_raw is not None else None))
        if len(rows) >= 20000:
            _batched_insert(con, sql, rows)
            rows.clear()
    if rows:
        _batched_insert(con, sql, rows)


def _load_primary_type(con: sqlite3.Connection, path: Path) -> None:
    rows = []
    for cols in _iter_tsv(path):
        if len(cols) < 2:
            continue
        rows.append((int(cols[0]), cols[1]))
    _batched_insert(con, "INSERT INTO release_group_primary_type(id, name) VALUES (?, ?)", rows)


def _load_secondary_type(con: sqlite3.Connection, path: Path) -> None:
    rows = []
    for cols in _iter_tsv(path):
        if len(cols) < 2:
            continue
        rows.append((int(cols[0]), cols[1]))
    _batched_insert(con, "INSERT INTO release_group_secondary_type(id, name) VALUES (?, ?)", rows)


def _load_secondary_join(con: sqlite3.Connection, path: Path) -> None:
    rows: list[tuple] = []
    sql = "INSERT INTO release_group_secondary_type_join(release_group, secondary_type) VALUES (?, ?)"
    for cols in _iter_tsv(path):
        if len(cols) < 2:
            continue
        rows.append((int(cols[0]), int(cols[1])))
        if len(rows) >= 20000:
            _batched_insert(con, sql, rows)
            rows.clear()
    if rows:
        _batched_insert(con, sql, rows)


def _fmt_bytes(n: int) -> str:
    value = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024.0 or unit == "TB":
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{n} B"


def build_fixture_catalog(db_path: Path) -> None:
    """Tiny catalog for unit tests (Ed Sheeran / Luke Combs / Life Goes On)."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    con = sqlite3.connect(str(db_path))
    try:
        con.executescript(
            """
            CREATE TABLE artist (id INTEGER PRIMARY KEY, gid TEXT NOT NULL, name TEXT NOT NULL);
            CREATE TABLE artist_alias (artist_id INTEGER NOT NULL, name TEXT NOT NULL);
            CREATE TABLE artist_credit (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
            CREATE TABLE artist_credit_name (
              artist_credit INTEGER NOT NULL, position INTEGER NOT NULL,
              artist_id INTEGER NOT NULL, name TEXT NOT NULL, join_phrase TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE release_group (
              id INTEGER PRIMARY KEY, gid TEXT NOT NULL, name TEXT NOT NULL,
              artist_credit INTEGER NOT NULL, primary_type_id INTEGER
            );
            CREATE TABLE release_group_meta (id INTEGER PRIMARY KEY, first_release_year INTEGER);
            CREATE TABLE release_group_primary_type (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
            CREATE TABLE release_group_secondary_type (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
            CREATE TABLE release_group_secondary_type_join (
              release_group INTEGER NOT NULL, secondary_type INTEGER NOT NULL
            );
            CREATE TABLE artist_rg (artist_id INTEGER NOT NULL, release_group_id INTEGER NOT NULL);
            """
        )
        con.executemany(
            "INSERT INTO release_group_primary_type(id, name) VALUES (?, ?)",
            [(1, "Album"), (2, "Single"), (3, "EP"), (4, "Other")],
        )
        # Luke Combs, Ed Sheeran
        con.executemany(
            "INSERT INTO artist(id, gid, name) VALUES (?, ?, ?)",
            [
                (1, "c20ee61f-071f-4e65-9c81-45ee931a54ce", "Luke Combs"),
                (2, "b8a7c51f-362c-4dcb-a259-bc6e0095f0a6", "Ed Sheeran"),
                (3, "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", "Shenandoah"),
            ],
        )
        con.execute(
            "INSERT INTO artist_alias(artist_id, name) VALUES (?, ?)",
            (2, "Edward Sheeran"),
        )
        con.execute(
            "INSERT INTO artist_credit(id, name) VALUES (?, ?)",
            (10, "Ed Sheeran feat. Luke Combs"),
        )
        con.executemany(
            "INSERT INTO artist_credit_name(artist_credit, position, artist_id, name, join_phrase) VALUES (?, ?, ?, ?, ?)",
            [
                (10, 0, 2, "Ed Sheeran", " feat. "),
                (10, 1, 1, "Luke Combs", ""),
            ],
        )
        con.execute(
            "INSERT INTO release_group(id, gid, name, artist_credit, primary_type_id) VALUES (?, ?, ?, ?, ?)",
            (100, "befae816-06e2-426d-aa51-6fcc6d93fca6", "Life Goes On", 10, 2),
        )
        con.execute(
            "INSERT INTO release_group_meta(id, first_release_year) VALUES (?, ?)",
            (100, 2023),
        )
        con.executemany(
            "INSERT INTO artist_rg(artist_id, release_group_id) VALUES (?, ?)",
            [(1, 100), (2, 100)],
        )
        # A second, differently-MBID'd "Ed Sheeran" row, and an unrelated
        # decoy release-group that also happens to be titled "Life Goes On"
        # (a common title) credited to a third artist — mirrors a real
        # MusicBrainz duplicate-artist-MBID situation, where the artist
        # Musicarr actually resolved isn't the one linked via artist_rg to
        # the real collab, and a same-titled unrelated release-group exists
        # to accidentally match against.
        con.execute(
            "INSERT INTO artist(id, gid, name) VALUES (?, ?, ?)",
            (6, "dddddddd-1111-2222-3333-444444444444", "Ed Sheeran"),
        )
        con.execute(
            "INSERT INTO artist(id, gid, name) VALUES (?, ?, ?)",
            (7, "eeeeeeee-1111-2222-3333-444444444444", "Some Other Band"),
        )
        con.execute("INSERT INTO artist_credit(id, name) VALUES (?, ?)", (13, "Some Other Band"))
        con.execute(
            "INSERT INTO artist_credit_name(artist_credit, position, artist_id, name, join_phrase) VALUES (?, ?, ?, ?, ?)",
            (13, 0, 7, "Some Other Band", ""),
        )
        con.execute(
            "INSERT INTO release_group(id, gid, name, artist_credit, primary_type_id) VALUES (?, ?, ?, ?, ?)",
            (104, "44444444-5555-6666-7777-888888888888", "Life Goes On", 13, 1),
        )
        con.execute("INSERT INTO release_group_meta(id, first_release_year) VALUES (?, ?)", (104, 1999))
        con.execute("INSERT INTO artist_rg(artist_id, release_group_id) VALUES (?, ?)", (7, 104))
        # Solo Luke album
        con.execute("INSERT INTO artist_credit(id, name) VALUES (?, ?)", (11, "Luke Combs"))
        con.execute(
            "INSERT INTO artist_credit_name(artist_credit, position, artist_id, name, join_phrase) VALUES (?, ?, ?, ?, ?)",
            (11, 0, 1, "Luke Combs", ""),
        )
        con.execute(
            "INSERT INTO release_group(id, gid, name, artist_credit, primary_type_id) VALUES (?, ?, ?, ?, ?)",
            (101, "11111111-2222-3333-4444-555555555555", "This One's for You", 11, 1),
        )
        con.execute("INSERT INTO release_group_meta(id, first_release_year) VALUES (?, ?)", (101, 2017))
        con.execute("INSERT INTO artist_rg(artist_id, release_group_id) VALUES (?, ?)", (1, 101))
        # Beyoncé (diacritic name) with a standard + deluxe edition of the same album,
        # for diacritic-folding and edition-distinction tests.
        con.execute(
            "INSERT INTO artist(id, gid, name) VALUES (?, ?, ?)",
            (4, "99999999-8888-7777-6666-555555555555", "Beyoncé"),
        )
        con.execute("INSERT INTO artist_credit(id, name) VALUES (?, ?)", (12, "Beyoncé"))
        con.execute(
            "INSERT INTO artist_credit_name(artist_credit, position, artist_id, name, join_phrase) VALUES (?, ?, ?, ?, ?)",
            (12, 0, 4, "Beyoncé", ""),
        )
        con.execute(
            "INSERT INTO release_group(id, gid, name, artist_credit, primary_type_id) VALUES (?, ?, ?, ?, ?)",
            (102, "22222222-3333-4444-5555-666666666666", "Renaissance", 12, 1),
        )
        con.execute(
            "INSERT INTO release_group(id, gid, name, artist_credit, primary_type_id) VALUES (?, ?, ?, ?, ?)",
            (103, "33333333-4444-5555-6666-777777777777", "Renaissance (Deluxe Edition)", 12, 1),
        )
        con.execute("INSERT INTO release_group_meta(id, first_release_year) VALUES (?, ?)", (102, 2022))
        con.execute("INSERT INTO release_group_meta(id, first_release_year) VALUES (?, ?)", (103, 2022))
        con.executemany(
            "INSERT INTO artist_rg(artist_id, release_group_id) VALUES (?, ?)",
            [(4, 102), (4, 103)],
        )
        con.executescript(
            """
            CREATE UNIQUE INDEX idx_artist_gid ON artist(gid);
            CREATE INDEX idx_artist_name ON artist(name COLLATE NOCASE);
            CREATE INDEX idx_artist_alias_name ON artist_alias(name COLLATE NOCASE);
            CREATE INDEX idx_acn_credit ON artist_credit_name(artist_credit);
            CREATE INDEX idx_rg_gid ON release_group(gid);
            CREATE INDEX idx_rg_name ON release_group(name COLLATE NOCASE);
            CREATE INDEX idx_artist_rg_artist ON artist_rg(artist_id);
            """
        )
        con.commit()
    finally:
        con.close()
