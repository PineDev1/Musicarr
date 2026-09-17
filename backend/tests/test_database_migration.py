from __future__ import annotations

from sqlalchemy import create_engine, inspect

from app.core.database import Base, migrate_schema


def _boot_sequence(engine):
    """Mirrors app.core.database.init_db()'s real order: create_all() runs
    before migrate_schema() on every startup, so anything migrate_schema does
    unconditionally must not undo what create_all() just created."""
    import app.models  # noqa: F401 register all model classes

    Base.metadata.create_all(bind=engine)
    migrate_schema(engine_=engine)


def test_boot_sequence_creates_and_keeps_indexer_tables(tmp_path):
    db_path = tmp_path / "boot.db"
    engine = create_engine(f"sqlite:///{db_path}")
    _boot_sequence(engine)
    tables = set(inspect(engine).get_table_names())
    assert {"indexers", "download_clients", "remote_path_mappings"} <= tables


def test_boot_sequence_survives_repeated_restarts(tmp_path):
    """A table created on boot 1 must still be there after boots 2 and 3 —
    regression guard for a prior bug where a leftover migration step dropped
    these tables again on every subsequent startup."""
    db_path = tmp_path / "boot.db"
    engine = create_engine(f"sqlite:///{db_path}")
    for _ in range(3):
        _boot_sequence(engine)
    tables = set(inspect(engine).get_table_names())
    assert {"indexers", "download_clients", "remote_path_mappings"} <= tables


def test_migrate_schema_alone_does_not_drop_existing_indexer_rows(tmp_path):
    from app.models import Indexer
    from sqlalchemy.orm import sessionmaker

    db_path = tmp_path / "boot.db"
    engine = create_engine(f"sqlite:///{db_path}")
    _boot_sequence(engine)

    Session = sessionmaker(bind=engine)
    session = Session()
    session.add(Indexer(name="Keep Me", base_url="https://x.tld", enabled=True))
    session.commit()
    session.close()

    # A second boot (create_all + migrate_schema again) must not wipe the row.
    _boot_sequence(engine)

    session = Session()
    row = session.query(Indexer).filter_by(name="Keep Me").one_or_none()
    session.close()
    assert row is not None
