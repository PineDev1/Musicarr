from __future__ import annotations

import pytest

from app.models import AppSettings
from app.services import library_roots


def _settings(db, tmp_path) -> AppSettings:
    row = AppSettings(id=1, library_path=str(tmp_path / "primary"))
    db.add(row)
    db.commit()
    return row


def test_add_root_and_list(db, tmp_path):
    _settings(db, tmp_path)
    extra = tmp_path / "extra"
    row = library_roots.add_root(db, path=str(extra), label="Old drive")
    assert row.id is not None
    assert extra.is_dir()

    rows = library_roots.list_extra_roots(db)
    assert len(rows) == 1
    assert rows[0].label == "Old drive"


def test_add_root_rejects_the_primary_path(db, tmp_path):
    _settings(db, tmp_path)
    with pytest.raises(ValueError):
        library_roots.add_root(db, path=str(tmp_path / "primary"))


def test_add_root_rejects_duplicate(db, tmp_path):
    _settings(db, tmp_path)
    extra = tmp_path / "extra"
    library_roots.add_root(db, path=str(extra))
    with pytest.raises(ValueError):
        library_roots.add_root(db, path=str(extra))


def test_all_library_roots_includes_primary_first(db, tmp_path):
    _settings(db, tmp_path)
    extra = tmp_path / "extra"
    library_roots.add_root(db, path=str(extra))

    roots = library_roots.all_library_roots(db)
    assert roots[0] == (tmp_path / "primary").resolve()
    assert (tmp_path / "extra").resolve() in roots


def test_all_library_roots_dedupes_nested_paths(db, tmp_path):
    _settings(db, tmp_path)
    (tmp_path / "primary" / "nested").mkdir(parents=True)
    library_roots.add_root(db, path=str(tmp_path / "primary" / "nested"))

    roots = library_roots.all_library_roots(db)
    # The "extra" root is a subdirectory of the primary — must not be
    # scanned twice (double-counting every file under it).
    assert len(roots) == 1


def test_remove_root(db, tmp_path):
    _settings(db, tmp_path)
    row = library_roots.add_root(db, path=str(tmp_path / "extra"))
    library_roots.remove_root(db, row.id)
    assert library_roots.list_extra_roots(db) == []


def test_remove_root_missing_raises(db, tmp_path):
    _settings(db, tmp_path)
    with pytest.raises(ValueError):
        library_roots.remove_root(db, 999)
