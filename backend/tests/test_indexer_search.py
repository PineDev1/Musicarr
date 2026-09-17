from __future__ import annotations

from unittest.mock import patch

from app.models import Indexer
from app.services.indexers.base import ReleaseCandidate
from app.services.indexers.search import pick_best, search_album


def _indexer(db, *, protocol="torrent", priority=25) -> Indexer:
    row = Indexer(
        name="Example",
        protocol=protocol,
        implementation="newznab",
        base_url="https://indexer.tld",
        api_key="key",
        enabled=True,
        priority=priority,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_search_album_scores_and_sorts_best_first(db):
    _indexer(db)
    hits = [
        ReleaseCandidate(title="Luke Combs - Fathers & Sons (2024) [FLAC]", size=400_000_000, seeders=20, protocol="torrent", magnet_url="magnet:?xt=1"),
        ReleaseCandidate(title="Luke Combs - Fathers & Sons (Karaoke Version)", size=400_000_000, seeders=50, protocol="torrent", magnet_url="magnet:?xt=2"),
        ReleaseCandidate(title="Random Unrelated Release", size=400_000_000, seeders=5, protocol="torrent", magnet_url="magnet:?xt=3"),
    ]
    with patch("app.services.indexers.search.search_newznab", return_value=hits):
        results = search_album(db, "Luke Combs", "Fathers & Sons", year="2024")

    assert len(results) == 3
    assert results[0].title.startswith("Luke Combs - Fathers & Sons (2024)")
    # sorted best-first
    assert results[0].score >= results[1].score >= results[2].score


def test_search_album_skips_disabled_indexer(db):
    row = _indexer(db)
    row.enabled = False
    db.commit()
    with patch("app.services.indexers.search.search_newznab") as fake:
        results = search_album(db, "Luke Combs", "Fathers & Sons")
    fake.assert_not_called()
    assert results == []


def test_search_album_continues_past_one_indexer_error(db):
    _indexer(db)
    from app.services.indexers.base import IndexerError

    with patch("app.services.indexers.search.search_newznab", side_effect=IndexerError("boom")):
        results = search_album(db, "Luke Combs", "Fathers & Sons")
    assert results == []  # doesn't raise


def test_pick_best_requires_min_score_and_grab_url():
    good = ReleaseCandidate(title="ok", score=50.0, magnet_url="magnet:?xt=1")
    no_url = ReleaseCandidate(title="no url", score=90.0, magnet_url="", download_url="")
    too_low = ReleaseCandidate(title="junk", score=5.0, magnet_url="magnet:?xt=2")

    assert pick_best([too_low, no_url, good]) is good
    assert pick_best([too_low, no_url]) is None
    assert pick_best([]) is None
