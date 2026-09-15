from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import Album, Artist, Track
from app.services.history import add_history
from app.services.providers import get_active_provider
from app.services.providers.base import ProviderError
from app.services.settings_service import ensure_settings


def _legacy_id(provider: str, provider_id: str) -> int:
    """Stable synthetic deezer_id for non-Deezer rows (process-independent)."""
    if provider == "deezer" and str(provider_id).isdigit():
        return int(provider_id)
    digest = hashlib.blake2b(f"{provider}:{provider_id}".encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") % 2_000_000_000


def album_type_allowed_for_artist(db: Session, artist: Artist, album_type: str) -> bool:
    settings = ensure_settings(db)
    if album_type == "single":
        # Per-artist override: False blocks singles; True allows; None inherits global
        override = getattr(artist, "include_singles", None)
        if override is False:
            return False
        if override is True:
            return True
    mapping = {
        "album": settings.include_albums,
        "ep": settings.include_eps,
        "single": settings.include_singles,
        "compilation": settings.include_compilations,
    }
    return mapping.get(album_type, False)


def link_artists_by_mbid(db: Session, mbid: str) -> list[Artist]:
    """Join all artist rows that share this MusicBrainz ID under one link_group_id."""
    key = (mbid or "").strip()
    if not key:
        return []
    rows = list(
        db.scalars(select(Artist).where(Artist.musicbrainz_id == key).order_by(Artist.id)).all()
    )
    if not rows:
        return []
    for row in rows:
        row.link_group_id = key
    db.commit()
    for row in rows:
        db.refresh(row)
    return rows


def merge_artists(db: Session, artist_ids: list[int], *, preferred_id: int | None = None) -> list[Artist]:
    """Merge artist rows into one link_group_id (same person across providers / collisions)."""
    ids = sorted({int(i) for i in artist_ids if i})
    if len(ids) < 2:
        raise ValueError("Select at least two artists to merge")
    rows = list(db.scalars(select(Artist).where(Artist.id.in_(ids)).order_by(Artist.id)).all())
    if len(rows) < 2:
        raise ValueError("Artists not found")
    preferred = next((r for r in rows if preferred_id and r.id == preferred_id), rows[0])
    mbids = [(getattr(r, "musicbrainz_id", None) or "").strip() for r in rows]
    mbids = [m for m in mbids if m]
    group = (getattr(preferred, "musicbrainz_id", None) or "").strip()
    if not group and mbids:
        group = mbids[0]
    if not group:
        existing = [(getattr(r, "link_group_id", None) or "").strip() for r in rows]
        existing = [g for g in existing if g]
        group = existing[0] if existing else f"merge:{preferred.id}"
    for row in rows:
        row.link_group_id = group
        if mbids and not (getattr(row, "musicbrainz_id", None) or "").strip():
            # Prefer a shared MBID when one exists
            if len(set(mbids)) == 1:
                row.musicbrainz_id = mbids[0]
    if mbids and len(set(mbids)) == 1:
        for row in rows:
            row.musicbrainz_id = mbids[0]
    db.commit()
    for row in rows:
        db.refresh(row)
    add_history(
        db,
        "artists_merged",
        f"Merged {len(rows)} artists as link group {group}",
    )
    return rows


def collision_groups(db: Session) -> list[list[Artist]]:
    """Groups of artists that share a normalized display name (2+ each)."""
    artists = list(db.scalars(select(Artist).order_by(Artist.name, Artist.id)).all())
    by_name: dict[str, list[Artist]] = {}
    for artist in artists:
        key = _norm_artist_name(artist.name)
        if not key:
            continue
        by_name.setdefault(key, []).append(artist)
    return [rows for rows in by_name.values() if len(rows) > 1]


def ensure_musicbrainz_identity(db: Session, artist: Artist) -> str | None:
    """Resolve + store MusicBrainz ID and link cross-provider peers."""
    from app.services import musicbrainz

    existing = (getattr(artist, "musicbrainz_id", None) or "").strip()
    if not existing:
        mbid = musicbrainz.resolve_artist(artist.name or "")
        if mbid:
            artist.musicbrainz_id = mbid
            db.commit()
            db.refresh(artist)
            existing = mbid
    if existing:
        link_artists_by_mbid(db, existing)
        db.refresh(artist)
    return existing or None


def _mb_provider_id(rg_mbid: str) -> str:
    return f"mb:{rg_mbid}"


def effective_provider_album_id(provider_id: str) -> str:
    """Strip collab:/mb:/mirror: wrappers to the underlying streaming id when present."""
    pid = (provider_id or "").strip()
    if pid.startswith("collab:") and pid.count(":") >= 2:
        return pid.split(":", 2)[-1]
    if pid.startswith("mirror:") and pid.count(":") >= 2:
        return pid.split(":", 2)[-1]
    if pid.startswith("mb:"):
        return pid
    return pid


def _extract_featured_names(*titles: str, primary_name: str | None = None) -> list[str]:
    import re

    found: list[str] = []
    seen: set[str] = set()
    primary_key = _norm_artist_name(primary_name or "")
    pattern = re.compile(
        r"(?:feat\.?|ft\.?|featuring)\s+([^(\[\]]+?)(?:\s*[)\]]|/|$)",
        re.I,
    )
    for title in titles:
        if not title:
            continue
        for match in pattern.finditer(title):
            raw = match.group(1)
            for part in re.split(r"\s*(?:,|&| and )\s*", raw, flags=re.I):
                name = " ".join(part.strip().split())
                key = _norm_artist_name(name)
                if len(name) < 2 or not key or key in seen:
                    continue
                if primary_key and key == primary_key:
                    continue
                seen.add(key)
                found.append(name)
    return found


def _album_collaborators(album: Album) -> list[str]:
    import json

    raw = getattr(album, "collaborators_json", None) or "[]"
    try:
        data = json.loads(raw) if isinstance(raw, str) else (raw or [])
    except json.JSONDecodeError:
        data = []
    out: list[str] = []
    for item in data:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
        elif isinstance(item, dict) and item.get("name"):
            out.append(str(item["name"]).strip())
    return out


def _set_album_collaborators(album: Album, names: list[str], *, primary_name: str = "") -> None:
    import json

    primary_key = _norm_artist_name(primary_name)
    cleaned: list[str] = []
    seen: set[str] = set()
    for name in names:
        key = _norm_artist_name(name)
        if not key or key in seen or (primary_key and key == primary_key):
            continue
        seen.add(key)
        cleaned.append(name.strip())
    album.collaborators_json = json.dumps(cleaned)


def _find_provider_album_for_rg(provider, artist_name: str, rg, provider_albums: list):
    from app.services import musicbrainz

    hit = musicbrainz.match_provider_album(rg, provider_albums)
    if hit:
        return hit
    search_fn = getattr(provider, "search_albums", None)
    if not callable(search_fn):
        return None
    try:
        query = f"{artist_name} {rg.title}".strip()
        hits = search_fn(query, limit=12)
    except Exception:  # noqa: BLE001
        return None
    return musicbrainz.match_provider_album(rg, hits or [])


def _clean_collab_title(title: str, primary_name: str) -> str:
    """Strip redundant (feat. Primary) from provider titles when MB has real credits."""
    import re

    t = (title or "").strip()
    if not t or not primary_name:
        return t
    escaped = re.escape(primary_name.strip())
    t = re.sub(
        rf"\s*[\(\[]\s*(?:feat\.?|ft\.?|featuring)\s+{escaped}\s*[\)\]]\s*",
        "",
        t,
        flags=re.I,
    )
    t = re.sub(r"\s{2,}", " ", t).strip(" -–—")
    return t or title


def _unique_provider_album_id(
    db: Session,
    *,
    provider_name: str,
    provider_id: str,
    artist_id: int,
) -> str:
    """Avoid global (provider, provider_id) clashes when two artists share a collab release."""
    pid = str(provider_id)
    # Unflushed session objects are invisible to SELECT — check identity map first.
    for obj in list(db.new) + list(db.dirty) + list(db.identity_map.values()):
        if not isinstance(obj, Album):
            continue
        if obj.provider == provider_name and str(obj.provider_id) == pid:
            if obj.artist_id == artist_id:
                return pid
            return f"collab:{artist_id}:{pid}"
    existing = db.scalar(
        select(Album).where(Album.provider == provider_name, Album.provider_id == pid)
    )
    if existing is None or existing.artist_id == artist_id:
        return pid
    return f"collab:{artist_id}:{pid}"


def _upsert_mb_album(
    db: Session,
    *,
    artist: Artist,
    rg,
    provider_hit,
    provider_name: str,
    existing_by_mbid: dict[str, Album],
    existing_by_pid: dict[str, Album],
    collaborator_names: list[str] | None = None,
    artist_credit: str = "",
) -> Album:
    from app.services import musicbrainz

    reason = ""
    credit = (artist_credit or "").strip()
    if provider_hit:
        status = "wanted"
        monitored = True
        raw_pid = str(provider_hit.provider_id)
        pid = _unique_provider_album_id(
            db, provider_name=provider_name, provider_id=raw_pid, artist_id=artist.id
        )
        # Prefer MusicBrainz title; strip redundant (feat. self) from provider titles
        title = rg.title or provider_hit.title or "Unknown"
        if not credit:
            title = provider_hit.title or title
        else:
            title = _clean_collab_title(title, artist.name) or title
        cover = provider_hit.cover_url or musicbrainz.cover_url_for_release_group(rg.mbid)
        release_date = provider_hit.release_date or (f"{rg.year}-01-01" if rg.year else None)
        track_count = provider_hit.track_count or 0
        album_type = provider_hit.album_type or rg.primary_type
    else:
        status = "missing"
        monitored = True
        pid = _mb_provider_id(rg.mbid)
        # Missing rows are per-artist via mb: uuid — still disambiguate if needed
        pid = _unique_provider_album_id(
            db, provider_name=provider_name, provider_id=pid, artist_id=artist.id
        )
        title = rg.title
        cover = musicbrainz.cover_url_for_release_group(rg.mbid)
        release_date = f"{rg.year}-01-01" if rg.year else None
        track_count = 0
        album_type = rg.primary_type
        reason = f"{provider_name.capitalize()} doesn't have this release"

    album = existing_by_mbid.get(rg.mbid) or existing_by_pid.get(pid)
    if album is None and provider_hit:
        # Also find by raw provider id before collab: prefix
        album = existing_by_pid.get(str(provider_hit.provider_id))
        if album and album.artist_id != artist.id:
            album = None
        elif album and album.artist_id == artist.id:
            pid = album.provider_id
    if album and (album.status or "") == "downloaded":
        album.musicbrainz_id = rg.mbid
        # Always refresh collab metadata on already-downloaded rows
        if credit:
            album.artist_credit = credit
            album.title = title or album.title
        elif not album.title:
            album.title = title
        album.cover_url = album.cover_url or cover
        if collaborator_names is not None:
            _set_album_collaborators(album, collaborator_names, primary_name=artist.name)
        if provider_hit and (album.provider_id or "").startswith("mb:"):
            album.provider_id = pid
            album.deezer_id = _legacy_id(provider_name, pid)
        return album

    if album is None:
        album = Album(
            provider=provider_name,
            provider_id=pid,
            deezer_id=_legacy_id(provider_name, pid),
            artist_id=artist.id,
            title=title,
            album_type=album_type,
            release_date=release_date,
            cover_url=cover,
            track_count=track_count,
            monitored=monitored,
            status=status,
            status_reason=reason,
            musicbrainz_id=rg.mbid,
            artist_credit=credit,
        )
        db.add(album)
        if collaborator_names is not None:
            _set_album_collaborators(album, collaborator_names, primary_name=artist.name)
        return album

    if provider_hit:
        from sqlalchemy import inspect as sa_inspect

        conflict = existing_by_pid.get(pid)
        if conflict is not None and conflict is not album:
            if (conflict.status or "") == "downloaded":
                # Keep the downloaded row; this album gets a disambiguated id.
                pid = f"collab:{artist.id}:{effective_provider_album_id(pid)}"
            else:
                insp = sa_inspect(conflict)
                if insp.persistent:
                    db.delete(conflict)
                elif insp.pending:
                    db.expunge(conflict)
                existing_by_pid.pop(conflict.provider_id, None)
        album.provider_id = pid
        album.deezer_id = _legacy_id(provider_name, pid)
        album.cover_url = cover
        album.track_count = track_count or album.track_count
        album.release_date = release_date or album.release_date
    album.title = title
    album.album_type = album_type
    album.musicbrainz_id = rg.mbid
    if credit:
        album.artist_credit = credit
    if collaborator_names is not None:
        _set_album_collaborators(album, collaborator_names, primary_name=artist.name)
    if (album.status or "") != "downloaded":
        if album.status == "skipped" and status == "wanted":
            album.status = "wanted"
            album.monitored = True
            album.status_reason = ""
        elif album.status != "skipped" or status == "missing":
            album.status = status
            album.monitored = monitored
            album.status_reason = reason
    return album


def album_display_artist(artist: Artist, album: Album) -> str:
    """Prefer MusicBrainz artist-credit for queue/UI labels."""
    credit = (getattr(album, "artist_credit", None) or "").strip()
    if credit:
        return credit
    collabs = _album_collaborators(album)
    if collabs:
        from app.services.tagging import format_credit_artist

        return format_credit_artist(artist.name, collabs)
    return artist.name or ""


def _artist_still_exists(db: Session, artist_id: int | None) -> bool:
    if not artist_id:
        return False
    return db.get(Artist, int(artist_id)) is not None


def _safe_commit_artist_sync(db: Session, artist: Artist) -> bool:
    """Commit album sync; abort cleanly if the artist was deleted mid-sync."""
    from sqlalchemy.orm.exc import ObjectDeletedError, StaleDataError

    if not _artist_still_exists(db, getattr(artist, "id", None)):
        db.rollback()
        return False
    try:
        artist.last_synced_at = datetime.now(timezone.utc)
        db.commit()
        return True
    except (StaleDataError, ObjectDeletedError):
        db.rollback()
        return False


def _sync_from_musicbrainz(
    db: Session,
    artist: Artist,
    *,
    provider,
    settings,
    provider_albums: list,
    discover_featured: bool = True,
) -> list[Album]:
    import json

    from app.services import musicbrainz
    from app.services.filters import is_junk_title, is_live_title

    mbid = ensure_musicbrainz_identity(db, artist)
    provider_name = artist.provider or provider.name

    if not mbid:
        add_history(
            db,
            "musicbrainz_unresolved",
            f"Could not resolve MusicBrainz artist for {artist.name}; provider albums kept for review",
        )
        # Fail open: keep provider albums as wanted so the library isn't empty
        return _sync_provider_albums(
            db,
            artist,
            provider_albums=provider_albums,
            settings=settings,
            gate_fn=lambda **_: ("wanted", True, ""),
        )

    catalog = musicbrainz.fetch_catalog(mbid)
    if catalog.error:
        add_history(
            db,
            "musicbrainz_error",
            f"MusicBrainz catalog failed for {artist.name}: {catalog.error}",
        )
        return _sync_provider_albums(
            db,
            artist,
            provider_albums=provider_albums,
            settings=settings,
            gate_fn=lambda **_: ("wanted", True, ""),
        )

    existing_rows = list(db.scalars(select(Album).where(Album.artist_id == artist.id)).all())
    existing_by_mbid = {
        (a.musicbrainz_id or "").strip(): a
        for a in existing_rows
        if (getattr(a, "musicbrainz_id", None) or "").strip()
    }
    existing_by_pid = {a.provider_id: a for a in existing_rows}

    matched_provider_ids: set[str] = set()
    touched: list[Album] = []
    monitor_mode = (getattr(artist, "monitor_mode", None) or "all").lower()
    cutoff = artist.added_at

    for rg in catalog.release_groups:
        # Match provider first (local list) — avoid enriching every single via MB.
        hit = musicbrainz.match_provider_album(rg, provider_albums)
        provider_title = getattr(hit, "title", None) or ""
        title_l = (rg.title or "").lower()
        looks_collab = (
            "feat" in title_l
            or " featuring" in title_l
            or "feat" in provider_title.lower()
            or " ft." in provider_title.lower()
            or " ft " in provider_title.lower()
        )
        type_ok = album_type_allowed_for_artist(db, artist, rg.primary_type)

        if not type_ok and not looks_collab:
            existing_rg = existing_by_mbid.get(rg.mbid)
            if existing_rg and (existing_rg.status or "") not in {"downloaded", "missing"}:
                if (existing_rg.album_type or rg.primary_type) == "single":
                    existing_rg.status = "skipped"
                    existing_rg.monitored = False
                    existing_rg.status_reason = "Singles disabled for this artist"
                    touched.append(existing_rg)
            continue

        # Enrich only when the title/provider already looks like a collab.
        # Do NOT enrich every single just to discover multi-credit (rate-limit death).
        if not rg.credits and looks_collab:
            musicbrainz.enrich_release_group_credits(rg)

        is_multi_credit = len(rg.credits) > 1
        our_on_credit = any(c.mbid == mbid for c in rg.credits)
        if not type_ok:
            if not (is_multi_credit and our_on_credit):
                continue

        if getattr(settings, "ignore_junk_titles", True) and is_junk_title(rg.title or ""):
            continue
        if getattr(settings, "ignore_live_releases", False) and is_live_title(rg.title or ""):
            continue
        if monitor_mode == "new" and rg.year and cutoff:
            try:
                added = cutoff.date() if hasattr(cutoff, "date") else cutoff
                if int(rg.year) < added.year:
                    continue
            except (ValueError, TypeError, AttributeError):
                pass

        if hit is None:
            # Local list only during bulk sync — remote search_albums per RG is too slow/noisy.
            hit = musicbrainz.match_provider_album(rg, provider_albums)
            provider_title = getattr(hit, "title", None) or ""
        if hit:
            matched_provider_ids.add(str(hit.provider_id))
        if not rg.credits and (
            "feat" in provider_title.lower()
            or " ft." in provider_title.lower()
            or " ft " in provider_title.lower()
        ):
            musicbrainz.enrich_release_group_credits(rg)
        title_feats = _extract_featured_names(
            rg.title,
            provider_title,
            primary_name=artist.name,
        )
        collab_names = list(
            dict.fromkeys(
                [
                    *musicbrainz.collaborator_names_for_rg(rg, mbid),
                    *title_feats,
                ]
            )
        )
        credit = musicbrainz.format_artist_credit(rg.credits)
        album = _upsert_mb_album(
            db,
            artist=artist,
            rg=rg,
            provider_hit=hit,
            provider_name=provider_name,
            existing_by_mbid=existing_by_mbid,
            existing_by_pid=existing_by_pid,
            collaborator_names=collab_names,
            artist_credit=credit,
        )
        existing_by_mbid[rg.mbid] = album
        existing_by_pid[album.provider_id] = album
        touched.append(album)

    # Provider-only albums not matched above — still resolve collab credits via MB search
    # Cap searches hard: each title can cost several MB calls and 503s cascade badly.
    max_collab_searches = 12
    collab_searches = 0
    for raw in provider_albums:
        pid = str(raw.provider_id)
        if pid in matched_provider_ids:
            continue
        album = existing_by_pid.get(pid)
        title_l = (raw.title or (album.title if album else "") or "").lower()
        looks_collab = "feat" in title_l or " ft." in title_l or " ft " in title_l
        if looks_collab and collab_searches < max_collab_searches:
            # Skip MB search for types this artist isn't monitoring (usually singles).
            if not album_type_allowed_for_artist(db, artist, raw.album_type or "single"):
                pass
            else:
                collab_searches += 1
                rg_hit = musicbrainz.search_release_group_for_artist(raw.title or "", mbid)
                if rg_hit:
                    matched_provider_ids.add(pid)
                    collab_names = musicbrainz.collaborator_names_for_rg(rg_hit, mbid)
                    credit = musicbrainz.format_artist_credit(rg_hit.credits)
                    album = _upsert_mb_album(
                        db,
                        artist=artist,
                        rg=rg_hit,
                        provider_hit=raw,
                        provider_name=provider_name,
                        existing_by_mbid=existing_by_mbid,
                        existing_by_pid=existing_by_pid,
                        collaborator_names=collab_names,
                        artist_credit=credit,
                    )
                    if (album.status or "") != "downloaded":
                        album.status = "wanted"
                        album.monitored = True
                        album.status_reason = ""
                    existing_by_mbid[rg_hit.mbid] = album
                    existing_by_pid[album.provider_id] = album
                    touched.append(album)
                    continue

        if not album_type_allowed_for_artist(db, artist, raw.album_type):
            continue
        if album and (album.status or "") == "downloaded":
            touched.append(album)
            continue
        if album is None:
            unique_pid = _unique_provider_album_id(
                db,
                provider_name=provider_name,
                provider_id=pid,
                artist_id=artist.id,
            )
            album = Album(
                provider=provider_name,
                provider_id=unique_pid,
                deezer_id=_legacy_id(provider_name, unique_pid),
                artist_id=artist.id,
                title=raw.title,
                album_type=raw.album_type,
                release_date=raw.release_date,
                cover_url=raw.cover_url,
                track_count=raw.track_count,
                monitored=False,
                status="skipped",
                status_reason="Not an official MusicBrainz release for this artist",
            )
            db.add(album)
            existing_by_pid[unique_pid] = album
        elif (album.status or "") != "downloaded":
            album.status = "skipped"
            album.monitored = False
            album.status_reason = "Not an official MusicBrainz release for this artist"
            album.title = raw.title or album.title
            album.cover_url = raw.cover_url or album.cover_url
        touched.append(album)

    if discover_featured:
        featured_names: list[str] = []
        collab_titles: list[str] = []
        for a in touched:
            if a.status not in {"wanted", "missing", "downloaded"}:
                continue
            names = _album_collaborators(a) or _extract_featured_names(
                a.title or "", primary_name=artist.name
            )
            credit = (getattr(a, "artist_credit", None) or "")
            if names:
                featured_names.extend(names)
                collab_titles.append(a.title or "")
            elif credit:
                for chunk in credit.replace(" feat. ", ",").replace(" & ", ",").split(","):
                    name = chunk.strip()
                    if name and _norm_artist_name(name) != _norm_artist_name(artist.name):
                        featured_names.append(name)
                        collab_titles.append(a.title or "")
        featured_names = list(dict.fromkeys(featured_names))
        # Commit primary catalog first so featured sync can't UNIQUE-clash on unflushed rows.
        if not _safe_commit_artist_sync(db, artist):
            return touched
        try:
            related = _ensure_featured_artists(
                db,
                primary=artist,
                featured_names=featured_names,
                provider_name=provider_name,
                collab_titles=collab_titles,
            )
            if not _artist_still_exists(db, artist.id):
                db.rollback()
                return touched
            artist.related_artists_json = json.dumps(related)
            if not _safe_commit_artist_sync(db, artist):
                return touched
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            if _artist_still_exists(db, artist.id):
                add_history(
                    db,
                    "featured_artist_error",
                    f"Featured artist sync failed for {artist.name}: {exc}",
                )
                db.commit()
    else:
        if not _safe_commit_artist_sync(db, artist):
            return touched

    for album in touched:
        try:
            db.refresh(album)
        except Exception:  # noqa: BLE001
            pass
    if _artist_still_exists(db, artist.id):
        try:
            db.refresh(artist)
        except Exception:  # noqa: BLE001
            pass
    return touched


def _ensure_featured_artists(
    db: Session,
    *,
    primary: Artist,
    featured_names: list[str],
    provider_name: str,
    collab_titles: list[str] | None = None,
) -> list[dict]:
    """Add collab artists with full MB catalog; auto-queue only shared releases."""
    from app.services.providers import get_provider
    from app.services.download_queue import download_queue

    provider = get_provider(db, provider_name)
    related: list[dict] = []
    primary_key = _norm_artist_name(primary.name)
    title_keys = {_norm_album_title(t) for t in (collab_titles or []) if t}
    # Also match cleaned titles
    title_keys |= {_norm_album_title(_clean_collab_title(t, primary.name)) for t in (collab_titles or []) if t}

    from sqlalchemy.exc import IntegrityError

    for name in featured_names[:12]:
        if _norm_artist_name(name) == primary_key:
            continue
        existing = db.scalar(
            select(Artist).where(Artist.name == name, Artist.provider == provider_name)
        )
        if existing is None:
            existing = find_artist_by_normalized_name(db, name, provider_name)
        if existing is None:
            try:
                hits = provider.search_artists(name, limit=5)
            except Exception:  # noqa: BLE001
                hits = []
            hit = next(
                (h for h in hits if _norm_artist_name(h.name) == _norm_artist_name(name)),
                hits[0] if hits else None,
            )
            if not hit:
                related.append({"id": None, "name": name, "musicbrainz_id": None, "provider": None})
                continue
            try:
                # Featured artists: albums + EPs only (not full singles catalog).
                # Shared collabs are still kept via multi-credit / title matching.
                existing = add_artist(
                    db,
                    hit.provider_id,
                    monitored=True,
                    download_missing=False,
                    provider_name=provider_name,
                    skip_featured=True,
                    include_singles=False,
                )
            except IntegrityError as exc:
                db.rollback()
                add_history(
                    db,
                    "featured_artist_error",
                    f"Could not add featured artist {name}: {exc}",
                )
                continue

        albums = list(db.scalars(select(Album).where(Album.artist_id == existing.id)).all())
        for album in albums:
            if (album.status or "") == "downloaded":
                continue
            title_key = _norm_album_title(album.title or "")
            collab_hit = bool(title_key and title_key in title_keys)
            mentions_primary = bool(primary_key and primary_key in (album.title or "").lower())
            collabs = _album_collaborators(album)
            credit = (getattr(album, "artist_credit", None) or "").lower()
            mentions_via_credit = any(
                _norm_artist_name(c) == primary_key for c in collabs
            ) or (primary_key and primary_key in credit)
            # Keep full MusicBrainz catalog visible (wanted/missing). Only auto-queue shared collabs.
            if collab_hit or mentions_primary or mentions_via_credit:
                if album.status == "missing":
                    album.monitored = True
                elif album.status != "wanted":
                    album.status = "wanted"
                    album.monitored = True
                    album.status_reason = ""
                download_queue.enqueue_album(db, album.id)
        db.commit()

        related.append(
            {
                "id": existing.id,
                "name": existing.name,
                "musicbrainz_id": getattr(existing, "musicbrainz_id", None),
                "provider": existing.provider,
            }
        )
    return related


def apply_collab_only_filter(
    db: Session,
    artist: Artist,
    *,
    keep_titles: list[str],
    primary_name: str,
) -> None:
    """Utility used by tests: keep only listed collab titles as wanted."""
    title_keys = {_norm_album_title(t) for t in keep_titles if t}
    primary_key = _norm_artist_name(primary_name)
    for album in db.scalars(select(Album).where(Album.artist_id == artist.id)).all():
        if (album.status or "") == "downloaded":
            continue
        title_key = _norm_album_title(album.title or "")
        keep = (title_key in title_keys) or (primary_key and primary_key in (album.title or "").lower())
        if keep and album.status != "missing":
            album.status = "wanted"
            album.monitored = True
            album.status_reason = ""
        elif not keep:
            album.status = "skipped"
            album.monitored = False
            album.status_reason = "Collaborator catalog — only shared releases are monitored"
    db.commit()


def _sync_provider_albums(
    db: Session,
    artist: Artist,
    *,
    provider_albums: list,
    settings,
    gate_fn,
) -> list[Album]:
    from app.services.filters import is_junk_title, is_live_title

    existing = {
        a.provider_id: a
        for a in db.scalars(select(Album).where(Album.artist_id == artist.id)).all()
    }
    monitor_mode = (getattr(artist, "monitor_mode", None) or "all").lower()
    cutoff = artist.added_at
    touched: list[Album] = []
    for raw in provider_albums:
        pid = raw.provider_id
        if pid in existing:
            album = existing[pid]
            album.title = raw.title or album.title
            album.cover_url = raw.cover_url or album.cover_url
            album.release_date = raw.release_date or album.release_date
            album.track_count = raw.track_count or album.track_count
            album.album_type = raw.album_type
            if (album.status or "") != "downloaded":
                status, monitored, reason = gate_fn(
                    title=album.title or raw.title or "",
                    year=album.release_date or raw.release_date,
                    album_type=album.album_type or raw.album_type or "album",
                )
                if album.status == "skipped" and status == "wanted":
                    album.status = "wanted"
                    album.monitored = True
                    album.status_reason = ""
                elif album.status != "skipped" or status == "skipped":
                    album.status = status
                    album.monitored = monitored
                    album.status_reason = reason or ""
            touched.append(album)
            continue
        if not album_type_allowed_for_artist(db, artist, raw.album_type):
            continue
        if getattr(settings, "ignore_junk_titles", True) and is_junk_title(raw.title or ""):
            continue
        if getattr(settings, "ignore_live_releases", False) and is_live_title(raw.title or ""):
            continue
        min_tracks = int(getattr(settings, "min_track_count", 0) or 0)
        if min_tracks > 0 and (raw.track_count or 0) > 0 and raw.track_count < min_tracks:
            if raw.album_type in {"album", "ep", "compilation"}:
                continue
        if monitor_mode == "new" and raw.release_date and cutoff:
            try:
                from datetime import date as date_cls

                rd = date_cls.fromisoformat(raw.release_date[:10])
                added = cutoff.date() if hasattr(cutoff, "date") else cutoff
                if rd < added:
                    continue
            except ValueError:
                pass

        status, monitored, reason = gate_fn(
            title=raw.title or "",
            year=raw.release_date,
            album_type=raw.album_type or "album",
        )
        unique_pid = _unique_provider_album_id(
            db,
            provider_name=artist.provider,
            provider_id=str(pid),
            artist_id=artist.id,
        )
        album = Album(
            provider=artist.provider,
            provider_id=unique_pid,
            deezer_id=_legacy_id(artist.provider, unique_pid),
            artist_id=artist.id,
            title=raw.title,
            album_type=raw.album_type,
            release_date=raw.release_date,
            cover_url=raw.cover_url,
            track_count=raw.track_count,
            monitored=monitored,
            status=status,
            status_reason=reason or "",
        )
        db.add(album)
        existing[unique_pid] = album
        touched.append(album)
    if not _safe_commit_artist_sync(db, artist):
        return touched
    for album in touched:
        try:
            db.refresh(album)
        except Exception:  # noqa: BLE001
            pass
    return touched


def sync_artist_albums(
    db: Session,
    artist: Artist,
    *,
    discover_featured: bool = True,
) -> list[Album]:
    if not artist.monitored or (getattr(artist, "monitor_mode", "all") or "all") == "none":
        return list(db.scalars(select(Album).where(Album.artist_id == artist.id)).all())

    if artist.provider == "local":
        return list(db.scalars(select(Album).where(Album.artist_id == artist.id)).all())

    provider = get_active_provider(db)
    if artist.provider != provider.name:
        from app.services.providers import get_provider

        provider = get_provider(db, artist.provider)

    settings = ensure_settings(db)
    raw_albums = provider.list_albums(artist.provider_id)
    official_only = bool(getattr(settings, "official_releases_only", True))

    if official_only:
        return _sync_from_musicbrainz(
            db,
            artist,
            provider=provider,
            settings=settings,
            provider_albums=raw_albums,
            discover_featured=discover_featured,
        )

    return _sync_provider_albums(
        db,
        artist,
        provider_albums=raw_albums,
        settings=settings,
        gate_fn=lambda **_: ("wanted", True, ""),
    )


def sync_album_tracks(db: Session, album: Album) -> list[Track]:
    from app.services.providers import get_provider

    stream_pid = effective_provider_album_id(album.provider_id or "")
    if stream_pid.startswith("mb:") or album.status == "missing" or not stream_pid:
        return list(album.tracks or [])

    provider = get_provider(db, album.provider)
    raw_tracks = provider.list_tracks(stream_pid)
    existing = {t.provider_id: t for t in album.tracks}
    result: list[Track] = []
    for raw in raw_tracks:
        if raw.provider_id in existing:
            track = existing[raw.provider_id]
            track.title = raw.title or track.title
            track.track_no = raw.track_no or track.track_no
            track.disc_no = raw.disc_no or track.disc_no
            track.duration = raw.duration or track.duration
            track.isrc = raw.isrc or track.isrc
            result.append(track)
            continue
        track = Track(
            provider=album.provider,
            provider_id=raw.provider_id,
            deezer_id=_legacy_id(album.provider, raw.provider_id),
            album_id=album.id,
            title=raw.title,
            track_no=raw.track_no,
            disc_no=raw.disc_no,
            duration=raw.duration,
            isrc=raw.isrc,
        )
        db.add(track)
        result.append(track)
    album.track_count = len(result) or album.track_count
    db.commit()
    return result


def add_artist(
    db: Session,
    provider_id: str,
    *,
    monitored: bool = True,
    download_missing: bool = True,
    provider_name: str | None = None,
    skip_featured: bool = False,
    include_singles: bool | None = None,
) -> Artist:
    settings = ensure_settings(db)
    pname = (provider_name or settings.active_provider or "deezer").lower()
    from app.services.providers import get_provider

    provider = get_provider(db, pname)

    existing = db.scalar(
        select(Artist).where(Artist.provider == pname, Artist.provider_id == str(provider_id))
    )
    if existing:
        if include_singles is not None:
            existing.include_singles = include_singles
            db.commit()
            db.refresh(existing)
        sync_artist_albums(db, existing, discover_featured=not skip_featured)
        if download_missing and monitored and not skip_featured:
            from app.services.download_queue import download_queue

            download_queue.enqueue_artist_missing(db, existing.id)
        return existing

    try:
        meta = provider.get_artist(str(provider_id))
    except ProviderError:
        raise

    artist = Artist(
        provider=pname,
        provider_id=str(provider_id),
        deezer_id=_legacy_id(pname, str(provider_id)),
        name=meta.name,
        image_url=meta.image_url,
        monitored=monitored,
        include_singles=include_singles,
    )
    db.add(artist)
    db.commit()
    db.refresh(artist)
    add_history(db, "artist_added", f"Added artist {artist.name} ({pname})")
    sync_artist_albums(db, artist, discover_featured=not skip_featured)
    db.refresh(artist)
    if download_missing and monitored and not skip_featured:
        from app.services.download_queue import download_queue

        download_queue.enqueue_artist_missing(db, artist.id)
    return artist


def get_artist_detail(db: Session, artist_id: int) -> Artist | None:
    return db.scalar(
        select(Artist)
        .options(joinedload(Artist.albums).joinedload(Album.tracks))
        .where(Artist.id == artist_id)
    )


def list_artists(db: Session) -> list[Artist]:
    return list(
        db.scalars(
            select(Artist).options(joinedload(Artist.albums)).order_by(Artist.name)
        )
        .unique()
        .all()
    )


def artist_stats(artist: Artist) -> tuple[int, int, int]:
    albums = artist.albums or []
    total = len(albums)
    downloaded = sum(1 for a in albums if a.status == "downloaded")
    wanted = sum(1 for a in albums if a.status == "wanted" and a.monitored)
    return total, downloaded, wanted


def _norm_artist_name(name: str) -> str:
    return " ".join((name or "").strip().lower().split())


def find_artist_by_normalized_name(db: Session, name: str, provider: str) -> Artist | None:
    """Find an artist by provider + normalized name (no silent row cap)."""
    key = _norm_artist_name(name)
    provider_key = (provider or "").strip()
    if not key or not provider_key:
        return None
    exact = db.scalar(
        select(Artist).where(Artist.provider == provider_key, Artist.name == (name or "").strip())
    )
    if exact and _norm_artist_name(exact.name) == key:
        return exact
    from sqlalchemy import func

    words = [w for w in key.split() if w]
    q = select(Artist).where(Artist.provider == provider_key)
    for word in words[:4]:
        q = q.where(func.lower(Artist.name).like(f"%{word}%"))
    candidates = list(db.scalars(q).all())
    matches = [a for a in candidates if _norm_artist_name(a.name) == key]
    if not matches:
        # Fallback: full provider scan only when LIKE was empty/too narrow
        if not words:
            return None
        all_rows = list(db.scalars(select(Artist).where(Artist.provider == provider_key)).all())
        matches = [a for a in all_rows if _norm_artist_name(a.name) == key]
    return matches[0] if matches else None


def _norm_album_title(title: str) -> str:
    import re

    t = (title or "").lower().strip()
    t = re.sub(r"\([^)]*\)", "", t)
    t = re.sub(r"\[[^\]]*\]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def find_linked_artists(db: Session, artist: Artist) -> list[Artist]:
    """Artists explicitly linked via link_group_id, otherwise just this row.

    Display-name twins are never auto-linked.
    """
    group_id = (getattr(artist, "link_group_id", None) or "").strip()
    if not group_id:
        detail = get_artist_detail(db, artist.id)
        return [detail or artist]
    rows = (
        db.scalars(
            select(Artist)
            .options(joinedload(Artist.albums).joinedload(Album.tracks))
            .where(Artist.link_group_id == group_id)
            .order_by(Artist.id)
        )
        .unique()
        .all()
    )
    return list(rows) if rows else [artist]


def _status_rank(status: str) -> int:
    return {"downloaded": 0, "wanted": 1, "missing": 2, "skipped": 3}.get(status or "", 9)


def merge_album_rows(
    albums: list[Album],
    *,
    active_provider: str = "deezer",
) -> list[tuple[Album, list[str]]]:
    """Collapse same-title albums within an explicit link group; keep best status row + source list."""
    groups: dict[str, list[Album]] = {}
    for album in albums:
        groups.setdefault(_norm_album_title(album.title) or f"id:{album.id}", []).append(album)

    merged: list[tuple[Album, list[str]]] = []
    for group in groups.values():
        sources = sorted({(a.provider or "deezer").lower() for a in group})
        group_sorted = sorted(
            group,
            key=lambda a: (
                _status_rank(a.status),
                0 if (a.provider or "").lower() == active_provider else 1,
                -(a.track_count or 0),
                a.id,
            ),
        )
        merged.append((group_sorted[0], sources))
    merged.sort(key=lambda item: (item[0].release_date or "", item[0].title), reverse=True)
    return merged


def grouped_artist_stats(
    artists: list[Artist], active_provider: str = "deezer"
) -> tuple[int, int, int, int]:
    all_albums: list[Album] = []
    for artist in artists:
        all_albums.extend(artist.albums or [])
    merged = merge_album_rows(all_albums, active_provider=active_provider)
    total = len(merged)
    downloaded = sum(1 for album, _ in merged if album.status == "downloaded")
    wanted = sum(1 for album, _ in merged if album.status == "wanted" and album.monitored)
    missing = sum(1 for album, _ in merged if album.status == "missing")
    return total, downloaded, wanted, missing


def list_artists_grouped(db: Session) -> list[list[Artist]]:
    """One group per artist, or per explicit link_group_id when set."""
    artists = list_artists(db)
    buckets: dict[str, list[Artist]] = {}
    order: list[str] = []
    for artist in artists:
        group_id = (getattr(artist, "link_group_id", None) or "").strip()
        key = f"link:{group_id}" if group_id else f"id:{artist.id}"
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(artist)
    return [buckets[k] for k in order]


def name_collision_ids(db: Session) -> set[int]:
    """Artist ids whose normalized display name is shared by another row."""
    artists = db.scalars(select(Artist)).all()
    by_name: dict[str, list[int]] = {}
    for artist in artists:
        key = _norm_artist_name(artist.name)
        if not key:
            continue
        by_name.setdefault(key, []).append(artist.id)
    collided: set[int] = set()
    for ids in by_name.values():
        if len(ids) > 1:
            collided.update(ids)
    return collided


def delete_artist(db: Session, artist_id: int) -> bool:
    """Delete only the requested artist row (never same-name strangers)."""
    artist = db.get(Artist, artist_id)
    if not artist:
        return False
    name = artist.name
    db.delete(artist)
    db.commit()
    add_history(db, "artist_removed", f"Removed artist {name}")
    return True


# Back-compat alias used by older call sites / tests
def delete_linked_artists(db: Session, artist_id: int) -> bool:
    return delete_artist(db, artist_id)


def mirror_downloaded_album_to_collaborators(db: Session, album: Album, primary: Artist) -> list[int]:
    """Hardlink/copy downloaded files under each collaborator's artist folder with correct tags."""
    import shutil
    from pathlib import Path

    from app.services.naming import artist_folder_name, build_album_folder, build_track_filename, year_from_release
    from app.services.settings_service import ensure_settings, library_root
    from app.services.tagging import format_credit_artist, write_track_tags
    from app.services.providers import get_provider

    collabs = _album_collaborators(album) or _extract_featured_names(
        album.title or "", primary_name=primary.name
    )
    if not collabs:
        return []

    settings = ensure_settings(db)
    root = library_root(db)
    year = year_from_release(album.release_date)
    credit = (getattr(album, "artist_credit", None) or "").strip() or format_credit_artist(
        primary.name, collabs
    )
    cover = Path(album.path) / "cover.jpg" if album.path else None
    if cover and not cover.exists():
        cover = None

    mirrored_ids: list[int] = []
    provider = get_provider(db, primary.provider)

    for name in collabs:
        if _norm_artist_name(name) == _norm_artist_name(primary.name):
            continue
        feat = db.scalar(
            select(Artist).where(Artist.provider == primary.provider, Artist.name == name)
        )
        if feat is None:
            feat = find_artist_by_normalized_name(db, name, primary.provider)
        if feat is None:
            try:
                hits = provider.search_artists(name, limit=5)
            except Exception:  # noqa: BLE001
                hits = []
            hit = next(
                (h for h in hits if _norm_artist_name(h.name) == _norm_artist_name(name)),
                hits[0] if hits else None,
            )
            if not hit:
                continue
            feat = add_artist(
                db,
                hit.provider_id,
                monitored=True,
                download_missing=False,
                provider_name=primary.provider,
                skip_featured=True,
                include_singles=False,
            )

        feat_album = None
        if album.musicbrainz_id:
            feat_album = db.scalar(
                select(Album).where(
                    Album.artist_id == feat.id,
                    Album.musicbrainz_id == album.musicbrainz_id,
                )
            )
        if feat_album is None:
            feat_album = next(
                (
                    a
                    for a in db.scalars(select(Album).where(Album.artist_id == feat.id)).all()
                    if _norm_album_title(a.title) == _norm_album_title(album.title)
                ),
                None,
            )
        if feat_album is None:
            mirror_pid = _unique_provider_album_id(
                db,
                provider_name=feat.provider,
                provider_id=f"mirror:{primary.id}:{effective_provider_album_id(album.provider_id or '')}",
                artist_id=feat.id,
            )
            feat_album = Album(
                provider=feat.provider,
                provider_id=mirror_pid,
                deezer_id=_legacy_id(feat.provider, mirror_pid),
                artist_id=feat.id,
                title=album.title,
                album_type=album.album_type,
                release_date=album.release_date,
                cover_url=album.cover_url,
                track_count=album.track_count,
                monitored=True,
                status="wanted",
                musicbrainz_id=album.musicbrainz_id,
                artist_credit=(getattr(album, "artist_credit", None) or ""),
            )
            db.add(feat_album)
            db.commit()
            db.refresh(feat_album)

        _set_album_collaborators(
            feat_album,
            [primary.name, *[c for c in collabs if _norm_artist_name(c) != _norm_artist_name(name)]],
            primary_name=feat.name,
        )

        folder_artist = artist_folder_name(feat, db=db)
        dest_folder = build_album_folder(
            root,
            settings.folder_template,
            artist=folder_artist,
            album=album.title,
            year=year,
            album_type=album.album_type,
        )
        dest_folder.mkdir(parents=True, exist_ok=True)
        if cover and cover.exists():
            target_cover = dest_folder / "cover.jpg"
            if not target_cover.exists():
                shutil.copy2(cover, target_cover)

        primary_tracks = sorted(
            [t for t in (album.tracks or []) if t.path],
            key=lambda t: (t.disc_no or 1, t.track_no or 0),
        )
        existing_tracks = {
            (t.disc_no or 1, t.track_no or 0): t for t in (feat_album.tracks or [])
        }
        for src_track in primary_tracks:
            src = Path(src_track.path)
            if not src.exists():
                continue
            filename = build_track_filename(
                settings.track_template,
                title=src_track.title,
                track=src_track.track_no or 0,
                disc=src_track.disc_no or 1,
                artist=feat.name,
                album=album.title,
                ext=src.suffix.lower(),
            )
            dest = dest_folder / filename
            if not dest.exists():
                try:
                    dest.hardlink_to(src)
                except OSError:
                    shutil.copy2(src, dest)
            write_track_tags(
                dest,
                title=src_track.title,
                artist=credit,
                album_artist=feat.name,
                album=album.title,
                track_no=src_track.track_no or 0,
                disc_no=src_track.disc_no or 1,
                year=year,
                cover_path=cover,
            )
            key = (src_track.disc_no or 1, src_track.track_no or 0)
            track = existing_tracks.get(key)
            if track is None:
                pid = f"{feat_album.provider_id}-t{key[0]}-{key[1]}"
                track = Track(
                    provider=feat.provider,
                    provider_id=pid,
                    deezer_id=_legacy_id(feat.provider, pid),
                    album_id=feat_album.id,
                    title=src_track.title,
                    track_no=src_track.track_no or 0,
                    disc_no=src_track.disc_no or 1,
                    duration=src_track.duration or 0,
                    isrc=src_track.isrc,
                    path=str(dest),
                )
                db.add(track)
            else:
                track.path = str(dest)
                track.title = src_track.title or track.title

        feat_album.path = str(dest_folder)
        feat_album.status = "downloaded"
        feat_album.quality = album.quality or feat_album.quality
        feat_album.monitored = True
        feat_album.status_reason = ""
        mirrored_ids.append(feat_album.id)

    db.commit()
    return mirrored_ids


def retag_downloaded_album(db: Session, album: Album, primary: Artist) -> None:
    """Fix album/track tags after download so credits are accurate."""
    from pathlib import Path

    from app.services.tagging import format_credit_artist, write_track_tags
    from app.services.naming import year_from_release

    credit = (getattr(album, "artist_credit", None) or "").strip()
    if not credit:
        collabs = _album_collaborators(album) or _extract_featured_names(
            album.title or "", primary_name=primary.name
        )
        credit = format_credit_artist(primary.name, collabs)
    year = year_from_release(album.release_date)
    cover = Path(album.path) / "cover.jpg" if album.path else None
    if cover and not cover.exists():
        cover = None
    for track in album.tracks or []:
        if not track.path:
            continue
        path = Path(track.path)
        if not path.exists():
            continue
        write_track_tags(
            path,
            title=track.title,
            artist=credit or primary.name,
            album_artist=primary.name,
            album=album.title,
            track_no=track.track_no or 0,
            disc_no=track.disc_no or 1,
            year=year,
            cover_path=cover,
        )
