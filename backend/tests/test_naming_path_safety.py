from __future__ import annotations

from app.services.naming import build_album_folder


def test_dotdot_in_artist_name_does_not_escape_root(tmp_path):
    root = tmp_path / "music"
    root.mkdir()
    folder = build_album_folder(
        root, "{artist}/{album} ({year})", artist="..", album="Album", year="2024"
    )
    assert root.resolve() in folder.parents or folder == root.resolve()


def test_sibling_directory_sharing_root_name_prefix_is_rejected(tmp_path):
    """A naive str.startswith() containment check would wrongly accept a
    sibling dir like '/data/music-private' for root '/data/music'."""
    root = tmp_path / "music"
    root.mkdir()
    sibling = tmp_path / "music-private"
    sibling.mkdir()
    folder = build_album_folder(root, "{artist}/{album}", artist="Artist", album="Album", year=None)
    assert not str(folder).startswith(str(sibling))
    assert str(folder).startswith(str(root.resolve()))


def test_normal_template_still_builds_expected_path(tmp_path):
    root = tmp_path / "music"
    root.mkdir()
    folder = build_album_folder(
        root, "{artist}/{album} ({year})", artist="Luke Combs", album="Fathers & Sons", year="2024"
    )
    assert folder == root.resolve() / "Luke Combs" / "Fathers & Sons (2024)"
