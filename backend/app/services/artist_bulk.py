from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models import Artist
from app.services.artists import clean_tags, delete_artist, find_linked_artists, parse_tags
from app.services.history import audit

ACTIONS = {
    "monitor",
    "unmonitor",
    "set_quality",
    "set_auto_grab",
    "add_tag",
    "remove_tag",
    "delete",
}
QUALITIES = {"flac", "320", "128"}


class BulkError(ValueError):
    pass


def _groups(db: Session, artist_ids: list[int]) -> list[list[Artist]]:
    """Distinct linked-artist groups for the ids (a group is one logical artist
    spread across providers — every edit must hit all its rows, like PATCH does)."""
    seen: set[int] = set()
    groups: list[list[Artist]] = []
    for aid in dict.fromkeys(artist_ids):
        if aid in seen:
            continue
        artist = db.get(Artist, aid)
        if not artist:
            continue
        rows = find_linked_artists(db, artist) or [artist]
        seen.update(r.id for r in rows)
        groups.append(rows)
    return groups


def apply_bulk_action(
    db: Session, artist_ids: list[int], action: str, value: Any = None
) -> dict[str, int]:
    if action not in ACTIONS:
        raise BulkError(f"Unknown action '{action}'")
    if not artist_ids:
        raise BulkError("Select at least one artist")
    if len(artist_ids) > 1000:
        raise BulkError("Too many artists in one request")

    if action == "set_quality" and value not in (None, "") and str(value) not in QUALITIES:
        raise BulkError("quality must be flac, 320, 128, or empty to inherit the default")
    if action == "set_auto_grab" and value not in (None, "", "on", "off"):
        raise BulkError("auto-grab must be on, off, or empty to inherit the default")
    if action in ("add_tag", "remove_tag") and not str(value or "").strip():
        raise BulkError("A tag is required")

    groups = _groups(db, artist_ids)
    affected = 0
    for rows in groups:
        if action == "delete":
            name = rows[0].name
            for row in rows:
                delete_artist(db, row.id)
            audit(db, "Artist removed (bulk)", f"{name}")
            affected += 1
            continue
        for row in rows:
            if action == "monitor":
                row.monitored = True
                row.monitor_mode = "all" if (row.monitor_mode or "none") == "none" else row.monitor_mode
            elif action == "unmonitor":
                row.monitored = False
                row.monitor_mode = "none"
            elif action == "set_quality":
                row.quality_pref = str(value) if value else None
            elif action == "set_auto_grab":
                row.auto_grab_override = value or None
            elif action in ("add_tag", "remove_tag"):
                tag = " ".join(str(value).split())
                current = parse_tags(row.tags_json)
                if action == "add_tag":
                    current = clean_tags([*current, tag])
                else:
                    current = [t for t in current if t.lower() != tag.lower()]
                row.tags_json = json.dumps(current)
        affected += 1
    db.commit()
    if action != "delete":
        audit(db, f"Bulk artist action '{action}'", f"{affected} artist(s)")
    return {"affected": affected, "requested": len(set(artist_ids))}
