from __future__ import annotations

from app.models import Album
from app.services.artists import _unique_provider_album_id
from tests.conftest import _artist


def test_returns_raw_pid_when_free(db):
    artist = _artist(db, name="A", provider="qobuz", provider_id="a1")
    pid = _unique_provider_album_id(
        db, provider_name="qobuz", provider_id="raw1", artist_id=artist.id
    )
    assert pid == "raw1"


def test_disambiguates_when_another_artist_owns_the_raw_id(db):
    owner = _artist(db, name="Owner", provider="qobuz", provider_id="o1")
    db.add(Album(provider="qobuz", provider_id="raw1", artist_id=owner.id, title="X"))
    db.commit()

    artist = _artist(db, name="A", provider="qobuz", provider_id="a1")
    pid = _unique_provider_album_id(
        db, provider_name="qobuz", provider_id="raw1", artist_id=artist.id
    )
    assert pid == f"collab:{artist.id}:raw1"


def test_extends_candidate_when_disambiguated_id_already_taken_by_someone_else(db):
    """Regression: a prior merge/reassignment can leave a
    'collab:{artist_id}:{pid}' string already claimed by a row that isn't
    this artist (its artist_id no longer matches the one embedded in the
    string). The naive "just prepend collab:{id}:" construction used to
    trust that string was free without checking — crashing the whole sync on
    a UNIQUE constraint violation when it collided with the stale row.
    """
    owner = _artist(db, name="Owner", provider="qobuz", provider_id="o1")
    db.add(Album(provider="qobuz", provider_id="raw1", artist_id=owner.id, title="X"))

    artist = _artist(db, name="A", provider="qobuz", provider_id="a1")
    # A stale row already sits on the exact string _unique_provider_album_id
    # would otherwise construct, but it belongs to a different artist today.
    stranded = Album(
        provider="qobuz",
        provider_id=f"collab:{artist.id}:raw1",
        artist_id=owner.id,
        title="Stranded from an earlier merge",
    )
    db.add(stranded)
    db.commit()

    pid = _unique_provider_album_id(
        db, provider_name="qobuz", provider_id="raw1", artist_id=artist.id
    )
    assert pid != f"collab:{artist.id}:raw1"
    assert pid == f"collab:{artist.id}:raw1:2"

    # And it must actually be free to insert without raising.
    db.add(Album(provider="qobuz", provider_id=pid, artist_id=artist.id, title="Real one"))
    db.commit()


def test_returns_raw_pid_unprefixed_when_this_artist_already_owns_it(db):
    artist = _artist(db, name="A", provider="qobuz", provider_id="a1")
    db.add(Album(provider="qobuz", provider_id="raw1", artist_id=artist.id, title="Mine"))
    db.commit()

    pid = _unique_provider_album_id(
        db, provider_name="qobuz", provider_id="raw1", artist_id=artist.id
    )
    assert pid == "raw1"
