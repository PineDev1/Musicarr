from __future__ import annotations

from app.services.artists import effective_provider_album_id


def test_effective_provider_album_id_plain():
    assert effective_provider_album_id("heyk2usghkh1b") == "heyk2usghkh1b"
    assert effective_provider_album_id("mb:uuid-here") == "mb:uuid-here"


def test_effective_provider_album_id_strips_collab_and_suffix():
    assert effective_provider_album_id("collab:5:raw1") == "raw1"
    assert effective_provider_album_id("collab:5:raw1:2") == "raw1"
    assert effective_provider_album_id("collab:12:mb:abcd-efgh") == "mb:abcd-efgh"
    assert effective_provider_album_id("collab:12:mb:abcd-efgh:3") == "mb:abcd-efgh"
    assert effective_provider_album_id("mirror:9:streamid") == "streamid"
