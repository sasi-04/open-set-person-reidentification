"""Database connection setup. The app stores metadata (who is enrolled, history, settings versions,
evaluation runs) in a small SQLite file.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Parent class of every table."""


def make_engine(url: str) -> Engine:
    engine = create_engine(url, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {})

    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_connection, _record) -> None:  # pragma: no cover - trivial
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")  # enforce relationships (and cascading deletes)
            cursor.execute("PRAGMA journal_mode=WAL")  # readers do not block the background job's writes
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def init_db(engine: Engine) -> None:
    """Create any missing tables and add any missing OPTIONAL columns. (A migration tool would replace this in production.)"""
    from . import models  # noqa: F401  - importing registers the tables on Base

    Base.metadata.create_all(engine)
    add_missing_columns(engine)


def add_missing_columns(engine: Engine) -> list[str]:
    """Upgrade an older database file in place when a release adds a nullable column to an existing
    table.
    """
    inspector = inspect(engine)
    added: list[str] = []
    preparer = engine.dialect.identifier_preparer
    with engine.begin() as connection:
        for table in Base.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue
            existing = {column["name"] for column in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing:
                    continue
                if not (column.nullable or column.server_default is not None):
                    logger.warning("Column %s.%s is missing and cannot be added automatically (NOT NULL without a default).", table.name, column.name)
                    continue
                kind = column.type.compile(dialect=engine.dialect)
                connection.execute(text(f"ALTER TABLE {preparer.quote(table.name)} ADD COLUMN {preparer.quote(column.name)} {kind}"))
                added.append(f"{table.name}.{column.name}")
    if added:
        logger.info("Database upgraded in place: added %s", ", ".join(added))
    return added


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    """``with session_scope(factory) as session:`` - commits on success, rolls back on error."""
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
