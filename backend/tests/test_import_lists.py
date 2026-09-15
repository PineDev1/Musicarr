from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from app.models import ImportList
from app.services import import_lists
from tests.conftest import _artist


def _fake_provider(hits_by_name: dict[str, list]):
    def search_artists(name, limit=5):
        return hits_by_name.get(name, [])

    return SimpleNamespace(name="qobuz", search_artists=search_artists)


def test_run_import_list_adds_new_skips_existing_and_reports_no_match(db):
    _artist(db, name="Already Here", provider="qobuz", provider_id="existing1")

    provider = _fake_provider(
        {
            "Already Here": [SimpleNamespace(name="Already Here", provider_id="existing1")],
            "Brand New Artist": [
                SimpleNamespace(name="Brand New Artist", provider_id="new1", nb_album=3)
            ],
            "Ambiguous Name": [
                SimpleNamespace(name="Ambiguous Name", provider_id="amb1"),
                SimpleNamespace(name="Ambiguous Name", provider_id="amb2"),
            ],
        }
    )

    import_list = ImportList(
        name="Test list",
        names_raw="Already Here\nBrand New Artist\nAmbiguous Name",
        interval_minutes=720,
        enabled=True,
    )
    db.add(import_list)
    db.commit()
    db.refresh(import_list)

    # add_artist itself (real provider fetch, album sync, download-queue
    # enqueue) is exercised elsewhere; this test is about run_import_list's
    # own logic — parsing names, skip-if-existing, confidence-gated
    # matching, and result/summary bookkeeping.
    with patch.object(import_lists, "get_active_provider", return_value=provider):
        with patch.object(import_lists, "add_artist") as mock_add_artist:
            result = import_lists.run_import_list(db, import_list)

    assert result["added"] == ["Brand New Artist"]
    assert result["skipped"] == ["Already Here"]
    assert len(result["errors"]) == 1
    assert "Ambiguous Name" in result["errors"][0]
    assert import_list.last_run_at is not None
    assert "1 added" in import_list.last_result
    mock_add_artist.assert_called_once_with(
        db,
        "new1",
        monitored=True,
        download_missing=True,
        provider_name="qobuz",
        require_approval=True,
        pending_reason="import_list",
    )


def test_due_import_lists_respects_interval(db):
    now = datetime.now(timezone.utc)
    never_run = ImportList(name="Never run", names_raw="X", interval_minutes=60, enabled=True)
    recently_run = ImportList(
        name="Recent",
        names_raw="X",
        interval_minutes=60,
        enabled=True,
        last_run_at=now - timedelta(minutes=5),
    )
    overdue = ImportList(
        name="Overdue",
        names_raw="X",
        interval_minutes=60,
        enabled=True,
        last_run_at=now - timedelta(minutes=90),
    )
    disabled_but_due = ImportList(
        name="Disabled",
        names_raw="X",
        interval_minutes=60,
        enabled=False,
        last_run_at=now - timedelta(minutes=90),
    )
    db.add_all([never_run, recently_run, overdue, disabled_but_due])
    db.commit()

    due = import_lists.due_import_lists(db, now=now)
    due_names = {row.name for row in due}
    assert due_names == {"Never run", "Overdue"}
