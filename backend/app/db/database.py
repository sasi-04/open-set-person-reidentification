"""
Database connection setup.

In plain words: the app stores metadata (who is enrolled, history, settings
versions, evaluation runs) in a small SQLite file. We talk to it only through
SQLAlchemy's ORM, which sends every value as a bound parameter - so there is no
string-built SQL anywhere and nothing to inject into. Because SQLAlchemy hides
the database dialect, moving to PostgreSQL later is a matter of changing the
connection URL (and adding a migration tool such as Alembic).
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
    """Upgrade an older database file in place when a release adds a nullable column to an existing table.

    ``create_all`` only creates tables that do not exist; it never alters one that does. Without this step, a database
    created by an earlier version would crash on the first query that mentions a new column - and the person's enrolled
    gallery would be unusable. Only columns that may be NULL (or have a server default) are added, because those are the
    only ones that can be added safely to a table that already holds rows. Nothing is ever dropped or rewritten.
    Returns the "table.column" names that were added.
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
