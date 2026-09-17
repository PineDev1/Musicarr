from __future__ import annotations

from unittest.mock import patch

import pytest

from app.services.indexers.base import IndexerError
from app.services.indexers.newznab import (
    api_endpoint,
    check_indexer_connection,
    search_newznab,
)

# Realistic torznab feed (trimmed Jackett/Prowlarr-style response) with one
# usable torrent item (magnet + seeders/size attrs) and one item that has no
# enclosure/link at all, which must be dropped rather than crash the parser.
TORZNAB_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:torznab="http://torznab.com/schemas/2015/feed">
  <channel>
    <title>Example Indexer</title>
    <item>
      <title>Some Artist - Some Album (2021) [FLAC]</title>
      <guid>abc123</guid>
      <link>magnet:?xt=urn:btih:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA&amp;dn=test</link>
      <enclosure url="magnet:?xt=urn:btih:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA&amp;dn=test" length="512000000" type="application/x-bittorrent" />
      <torznab:attr name="size" value="512000000" />
      <torznab:attr name="seeders" value="42" />
      <torznab:attr name="peers" value="50" />
      <torznab:attr name="category" value="3040" />
    </item>
    <item>
      <title>No download link at all</title>
      <guid>def456</guid>
    </item>
  </channel>
</rss>
"""

NEWZNAB_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:newznab="http://www.newznab.com/DTD/2010/feeds/attributes/">
  <channel>
    <item>
      <title>Some.Artist-Some.Album-2021-FLAC</title>
      <link>https://indexer.example/getnzb/xyz.nzb</link>
      <enclosure url="https://indexer.example/getnzb/xyz.nzb" length="734003200" type="application/x-nzb" />
      <newznab:attr name="size" value="734003200" />
    </item>
  </channel>
</rss>
"""

ERROR_XML = """<?xml version="1.0" encoding="UTF-8"?>
<error code="100" description="Incorrect user credentials" />
"""

CAPS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<caps><server version="1.0" title="Example" /></caps>
"""


def test_api_endpoint_variants():
    assert api_endpoint("https://indexer.tld") == "https://indexer.tld/api"
    assert api_endpoint("https://indexer.tld/api") == "https://indexer.tld/api"
    assert api_endpoint("indexer.tld") == "http://indexer.tld/api"
    with pytest.raises(IndexerError):
        api_endpoint("")


def test_search_newznab_parses_torznab_items_and_drops_linkless_ones():
    with patch("app.services.indexers.newznab._get", return_value=TORZNAB_XML):
        results = search_newznab("https://indexer.tld", "key123", "Some Album", protocol="torrent")
    assert len(results) == 1
    hit = results[0]
    assert hit.title == "Some Artist - Some Album (2021) [FLAC]"
    assert hit.size == 512000000
    # peers(50) - explicit seeders(42) attr present -> seeders attr wins
    assert hit.seeders == 42
    assert hit.magnet_url.startswith("magnet:")
    assert hit.grab_url == hit.magnet_url


def test_search_newznab_parses_nzb_enclosure():
    with patch("app.services.indexers.newznab._get", return_value=NEWZNAB_XML):
        results = search_newznab("https://indexer.tld", "key123", "Some Album", protocol="usenet")
    assert len(results) == 1
    assert results[0].download_url == "https://indexer.example/getnzb/xyz.nzb"
    assert results[0].magnet_url == ""
    assert results[0].grab_url == results[0].download_url


def test_search_newznab_falls_back_to_music_search_on_empty_generic_hit():
    calls = []

    def fake_get(url, params):
        calls.append(params.get("t"))
        if params.get("t") == "search":
            return "<rss><channel></channel></rss>"
        return TORZNAB_XML

    with patch("app.services.indexers.newznab._get", side_effect=fake_get):
        results = search_newznab(
            "https://indexer.tld", "key", "Some Album", protocol="torrent", artist="Some Artist", album="Some Album"
        )
    assert calls == ["search", "music"]
    assert len(results) == 1


def test_search_newznab_raises_on_error_response():
    with patch("app.services.indexers.newznab._get", return_value=ERROR_XML):
        with pytest.raises(IndexerError):
            search_newznab("https://indexer.tld", "key", "query")


def test_check_indexer_connection_success_and_failure():
    with patch("app.services.indexers.newznab._get", return_value=CAPS_XML):
        ok, message = check_indexer_connection("https://indexer.tld", "key")
    assert ok is True
    assert "indexer.tld" in message

    with patch("app.services.indexers.newznab._get", return_value=ERROR_XML):
        ok, message = check_indexer_connection("https://indexer.tld", "bad-key")
    assert ok is False
    assert "credentials" in message.lower()
