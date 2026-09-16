from __future__ import annotations

import logging
import sqlite3
import threading
from difflib import SequenceMatcher
from pathlib import Path

from app.services.mb_catalog_paths import catalog_db_path
from app.services.musicbrainz import (
    CatalogResult,
    CreditArtist,
    ReleaseGroup,
    _map_primary_type,
    _should_keep_rg,
    normalize_title,
    normalize_title_strict,
)
from app.services.text_match import fold_diacritics, normalize_key

logger = logging.getLogger("musicarr.mb_local")

_lock = threading.Lock()
_db_path: Path | None = None
_conn: sqlite3.Connection | None = None


def configure(path: Path | None = None) -> None:
    global _db_path, _conn
    with _lock:
        if _conn is not None:
            try:
                _conn.close()
            except Exception:  # noqa: BLE001
                pass
            _conn = None
        _db_path = path


def reload() -> None:
    configure(_db_path)


def is_available() -> bool:
    path = _db_path or catalog_db_path()
    return path.is_file() and path.stat().st_size > 0


def _unaccent_lower(text: str | None) -> str:
    return fold_diacritics((text or "")).lower()


def _connect() -> sqlite3.Connection:
    global _conn, _db_path
    with _lock:
        path = _db_path or catalog_db_path()
        if _conn is not None:
            return _conn
        if not path.is_file():
            raise FileNotFoundError(f"MusicBrainz catalog not found: {path}")
        _conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        # Lets WHERE clauses compare diacritic-folded text (e.g. a "Beyonce"
        # query matching a "Beyoncé" row) without needing to alter the
        # read-only catalog file itself.
        _conn.create_function("unaccent_lower", 1, _unaccent_lower)
        return _conn


def resolve_artist(name: str, *, fast: bool = False) -> str | None:
    """Resolve a name to an MBID.

    `fast=True` skips the substring/diacritic fallback scans below (each a
    full table scan over the local catalog — fine for a single lookup, too
    slow to run per-result across a 25-result search list) and only returns
    exact name/alias matches. Used by the artist-search endpoint, where a
    miss just means no album-count badge; real resolution still happens
    later (with the full fallback chain) when the artist is actually added.
    """
    q = (name or "").strip()
    if not q:
        return None
    con = _connect()
    # Exact name / alias (indexed, case-insensitive) — cheap, covers most hits.
    row = con.execute(
        """
        SELECT gid FROM artist WHERE name = ? COLLATE NOCASE
        UNION
        SELECT a.gid FROM artist a
        JOIN artist_alias aa ON aa.artist_id = a.id
        WHERE aa.name = ? COLLATE NOCASE
        LIMIT 1
        """,
        (q, q),
    ).fetchone()
    if row:
        return str(row["gid"])
    if fast:
        return None
    # Native substring scan (no per-row Python call — fast even unindexed).
    # Catches typos/partial matches whenever the query and the DB name still
    # share a literal run of characters, which most do.
    like = f"%{q}%"
    rows = con.execute(
        """
        SELECT gid, name FROM artist
        WHERE name LIKE ? COLLATE NOCASE
        ORDER BY LENGTH(name) ASC
        LIMIT 25
        """,
        (like,),
    ).fetchall()
    best_gid, best_score = _score_artist_rows(q, rows)
    if best_gid and best_score >= 0.86:
        return best_gid
    # Last resort: a diacritic-folded scan. This calls into Python for every
    # row (no index can help once the text needs folding first), so it's
    # meaningfully slower — only pay for it when the cheap paths above found
    # nothing, e.g. "Beyonce" vs a DB row spelled "Beyoncé" with no ASCII
    # alias and no shared literal substring.
    qkey = _unaccent_lower(q)
    like_folded = f"%{qkey}%"
    rows = con.execute(
        """
        SELECT gid, name FROM artist
        WHERE unaccent_lower(name) LIKE ?
        ORDER BY LENGTH(name) ASC
        LIMIT 25
        """,
        (like_folded,),
    ).fetchall()
    best_gid, best_score = _score_artist_rows(q, rows)
    if best_gid and best_score >= 0.86:
        return best_gid
    return None


def _score_artist_rows(query: str, rows: list[sqlite3.Row]) -> tuple[str | None, float]:
    best_gid: str | None = None
    best_score = 0.0
    qn = normalize_title(query)
    for row in rows:
        score = SequenceMatcher(None, qn, normalize_title(row["name"])).ratio()
        if score > best_score:
            best_score = score
            best_gid = str(row["gid"])
    return best_gid, best_score


def _credits_for_artist_credit(con: sqlite3.Connection, credit_id: int) -> tuple[CreditArtist, ...]:
    rows = con.execute(
        """
        SELECT acn.name AS credit_name, acn.join_phrase, a.gid, a.name AS artist_name
        FROM artist_credit_name acn
        JOIN artist a ON a.id = acn.artist_id
        WHERE acn.artist_credit = ?
        ORDER BY acn.position ASC
        """,
        (credit_id,),
    ).fetchall()
    out: list[CreditArtist] = []
    for row in rows:
        out.append(
            CreditArtist(
                mbid=str(row["gid"] or ""),
                name=str(row["credit_name"] or row["artist_name"] or ""),
                joinphrase=str(row["join_phrase"] or ""),
            )
        )
    return tuple(out)


def _secondary_types(con: sqlite3.Connection, rg_id: int) -> tuple[str, ...]:
    rows = con.execute(
        """
        SELECT st.name
        FROM release_group_secondary_type_join j
        JOIN release_group_secondary_type st ON st.id = j.secondary_type
        WHERE j.release_group = ?
        """,
        (rg_id,),
    ).fetchall()
    return tuple(str(r["name"]) for r in rows)


def _row_to_rg(con: sqlite3.Connection, row: sqlite3.Row, *, with_credits: bool) -> ReleaseGroup | None:
    secondary = _secondary_types(con, int(row["id"]))
    if not _should_keep_rg(list(secondary)):
        return None
    primary_name = row["primary_type_name"]
    year = ""
    if row["first_release_year"] is not None:
        year = str(int(row["first_release_year"]))
    credits: tuple[CreditArtist, ...] = ()
    if with_credits:
        credits = _credits_for_artist_credit(con, int(row["artist_credit"]))
    return ReleaseGroup(
        mbid=str(row["gid"]),
        title=str(row["name"]),
        primary_type=_map_primary_type(primary_name, list(secondary)),
        year=year,
        secondary_types=secondary,
        credits=credits,
    )


def fetch_catalog(mbid: str) -> CatalogResult:
    key = (mbid or "").strip()
    if not key:
        return CatalogResult(error="No MusicBrainz artist id")
    try:
        con = _connect()
    except FileNotFoundError as exc:
        return CatalogResult(error=str(exc))

    artist = con.execute("SELECT id FROM artist WHERE gid = ?", (key,)).fetchone()
    if not artist:
        return CatalogResult(error=f"Artist not found in local catalog: {key}")

    rows = con.execute(
        """
        SELECT rg.id, rg.gid, rg.name, rg.artist_credit, rg.primary_type_id,
               pt.name AS primary_type_name, meta.first_release_year
        FROM artist_rg ar
        JOIN release_group rg ON rg.id = ar.release_group_id
        LEFT JOIN release_group_primary_type pt ON pt.id = rg.primary_type_id
        LEFT JOIN release_group_meta meta ON meta.id = rg.id
        WHERE ar.artist_id = ?
        ORDER BY CASE WHEN meta.first_release_year IS NULL THEN 1 ELSE 0 END,
                 meta.first_release_year DESC, rg.name COLLATE NOCASE
        """,
        (int(artist["id"]),),
    ).fetchall()

    out: list[ReleaseGroup] = []
    collaborators: dict[str, CreditArtist] = {}
    for row in rows:
        rg = _row_to_rg(con, row, with_credits=True)
        if not rg:
            continue
        out.append(rg)
        for c in rg.credits:
            if c.mbid and c.mbid != key:
                collaborators[c.mbid] = c
    return CatalogResult(release_groups=out, collaborators=list(collaborators.values()))


def count_release_groups(mbid: str) -> int | None:
    """Count catalog release-groups for an artist (same filters as fetch_catalog)."""
    key = (mbid or "").strip()
    if not key:
        return None
    try:
        con = _connect()
    except FileNotFoundError:
        return None

    artist = con.execute("SELECT id FROM artist WHERE gid = ?", (key,)).fetchone()
    if not artist:
        return None

    rows = con.execute(
        """
        SELECT rg.id, pt.name AS primary_type_name
        FROM artist_rg ar
        JOIN release_group rg ON rg.id = ar.release_group_id
        LEFT JOIN release_group_primary_type pt ON pt.id = rg.primary_type_id
        WHERE ar.artist_id = ?
        """,
        (int(artist["id"]),),
    ).fetchall()
    if not rows:
        return 0

    # Batch-fetch secondary types for every release group at once instead of
    # one query per row (this loop used to be an N+1 that dominated search
    # latency: up to ~25 artists per search, each with dozens of release
    # groups, each needing its own secondary-type lookup).
    rg_ids = [int(r["id"]) for r in rows]
    placeholders = ",".join("?" * len(rg_ids))
    secondary_by_rg: dict[int, list[str]] = {rid: [] for rid in rg_ids}
    for j_row in con.execute(
        f"""
        SELECT j.release_group AS rg_id, st.name
        FROM release_group_secondary_type_join j
        JOIN release_group_secondary_type st ON st.id = j.secondary_type
        WHERE j.release_group IN ({placeholders})
        """,
        rg_ids,
    ).fetchall():
        secondary_by_rg[int(j_row["rg_id"])].append(str(j_row["name"]))

    total = 0
    for row in rows:
        secondary = secondary_by_rg[int(row["id"])]
        if not _should_keep_rg(secondary):
            continue
        if _map_primary_type(row["primary_type_name"], secondary) != "other":
            total += 1
    return total


def enrich_release_group_credits(rg: ReleaseGroup) -> ReleaseGroup:
    if rg.credits or not rg.mbid:
        return rg
    try:
        con = _connect()
    except FileNotFoundError:
        return rg
    row = con.execute(
        "SELECT id, artist_credit FROM release_group WHERE gid = ?",
        (rg.mbid,),
    ).fetchone()
    if not row:
        return rg
    rg.credits = _credits_for_artist_credit(con, int(row["artist_credit"]))
    return rg


def search_release_group_for_artist(
    title: str,
    artist_mbid: str,
    *,
    limit: int = 5,
) -> ReleaseGroup | None:
    import re

    search_title = re.sub(
        r"\s*[\(\[][^)\]]*(?:feat\.?|ft\.?|featuring)[^)\]]*[\)\]]",
        "",
        title or "",
        flags=re.I,
    ).strip() or (title or "")
    search_title = re.sub(
        r"\s*(?:feat\.?|ft\.?|featuring)\s+.+$",
        "",
        search_title,
        flags=re.I,
    ).strip() or search_title
    clean = normalize_title(search_title)
    clean_strict = normalize_title_strict(search_title)
    aid = (artist_mbid or "").strip()
    if not clean or not aid:
        return None
    try:
        con = _connect()
    except FileNotFoundError:
        return None

    artist = con.execute("SELECT id, name FROM artist WHERE gid = ?", (aid,)).fetchone()
    artist_id = int(artist["id"]) if artist else None
    # MusicBrainz occasionally has more than one artist entry for the same
    # real person (e.g. two distinct "Ed Sheeran" MBIDs); a release-group's
    # credits might name our artist without crediting the exact MBID we
    # resolved to. Fall back to a name match so that still counts.
    artist_name_key = normalize_key(str(artist["name"])) if artist else ""

    def _query(name_clause: str, like_value: str) -> list[sqlite3.Row]:
        # When the artist is known, join from artist_rg (indexed on artist_id)
        # so the name filter only ever runs over that artist's own release
        # groups (tens of rows) instead of a full unindexed scan of all
        # release groups (millions of rows) with an EXISTS check per hit.
        if artist_id is not None:
            sql = f"""
                SELECT rg.id, rg.gid, rg.name, rg.artist_credit, rg.primary_type_id,
                       pt.name AS primary_type_name, meta.first_release_year
                FROM artist_rg ar
                JOIN release_group rg ON rg.id = ar.release_group_id
                LEFT JOIN release_group_primary_type pt ON pt.id = rg.primary_type_id
                LEFT JOIN release_group_meta meta ON meta.id = rg.id
                WHERE ar.artist_id = ? AND {name_clause} LIKE ?
                LIMIT ?
            """
            params: list[object] = [artist_id, like_value, max(limit * 4, 20)]
        else:
            sql = f"""
                SELECT rg.id, rg.gid, rg.name, rg.artist_credit, rg.primary_type_id,
                       pt.name AS primary_type_name, meta.first_release_year
                FROM release_group rg
                LEFT JOIN release_group_primary_type pt ON pt.id = rg.primary_type_id
                LEFT JOIN release_group_meta meta ON meta.id = rg.id
                WHERE {name_clause} LIKE ?
                LIMIT ?
            """
            params = [like_value, max(limit * 4, 20)]
        return con.execute(sql, params).fetchall()

    # Native (unindexed but fast — no per-row Python call) substring match first.
    like = f"%{search_title}%"
    rows = _query("rg.name", like)
    if not rows:
        # Diacritic-folded fallback: slower (a Python call per candidate row),
        # so only pay for it when the cheap native scan found nothing.
        like_folded = f"%{_unaccent_lower(search_title)}%"
        rows = _query("unaccent_lower(rg.name)", like_folded)
    # Wide search if arid-scoped miss and title looks like a collab. This is a
    # last resort (e.g. the target artist has a second, differently-credited
    # MBID in MusicBrainz — see artist_name_key above), so it's worth paying
    # for a much wider candidate pool: common titles like "Life Goes On" have
    # 80+ unrelated release-groups, and the real match won't necessarily be
    # among the first 20 SQLite happens to return.
    if not rows and re.search(r"feat\.?|ft\.?|featuring", title or "", re.I):
        # Each row here costs a couple of extra queries (secondary types +
        # credits) in _row_to_rg below, and this path runs on every periodic
        # monitor tick for any artist stuck on a duplicate MBID — so the
        # limit has to stay modest even though a wider pool improves recall.
        rows = con.execute(
            """
            SELECT rg.id, rg.gid, rg.name, rg.artist_credit, rg.primary_type_id,
                   pt.name AS primary_type_name, meta.first_release_year
            FROM release_group rg
            LEFT JOIN release_group_primary_type pt ON pt.id = rg.primary_type_id
            LEFT JOIN release_group_meta meta ON meta.id = rg.id
            WHERE rg.name LIKE ?
            LIMIT ?
            """,
            (like, 80),
        ).fetchall()

    best: ReleaseGroup | None = None
    best_score = 0.0
    for row in rows:
        rg = _row_to_rg(con, row, with_credits=True)
        if not rg:
            continue
        cand = normalize_title(rg.title)
        ratio = SequenceMatcher(None, clean, cand).ratio()
        if cand == clean or clean in cand or cand in clean:
            ratio = 1.0
        # Prefer the release-group whose edition wording actually matches the
        # query instead of treating every edition as interchangeable once the
        # noise-stripped titles tie (e.g. "Album (Deluxe)" vs "Album (Live)").
        if clean_strict and normalize_title_strict(rg.title) == clean_strict:
            ratio += 0.1
        credit_mbids = {c.mbid for c in rg.credits}
        credit_name_keys = {normalize_key(c.name) for c in rg.credits}
        credited = aid in credit_mbids or (artist_name_key and artist_name_key in credit_name_keys)
        if rg.credits and not credited:
            # This release-group has known credits and none of them are our
            # artist (by id or name) — never a valid match, regardless of how
            # well the bare title happens to line up (e.g. many different
            # artists have released songs called "Life Goes On").
            continue
        if credited:
            ratio += 0.15
        if ratio > best_score:
            best_score = ratio
            best = rg
            if credited and ratio >= 0.98:
                # Near-exact title, correctly credited — not going to do
                # better than this among the remaining candidates.
                break
    if best and best_score >= 0.75:
        return best
    return None
