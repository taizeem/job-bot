"""
SQLAlchemy 2.0 engine and session factory.

Provides:
- ``engine`` — the global :class:`~sqlalchemy.engine.Engine` instance.
- ``SessionLocal`` — a :func:`~sqlalchemy.orm.sessionmaker` bound to the engine.
- ``get_db()`` — a FastAPI-compatible dependency that yields a session.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings


def _build_engine() -> Engine:
    """Create the SQLAlchemy engine from application settings.

    For SQLite connections, ``check_same_thread`` is set to ``False``
    so that the engine can be shared across threads (required by FastAPI).

    Returns:
        A configured :class:`~sqlalchemy.engine.Engine`.
    """
    connect_args: dict[str, Any] = {}
    if settings.database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    return create_engine(
        settings.database_url,
        connect_args=connect_args,
        echo=False,
        pool_pre_ping=True,
    )


engine: Engine = _build_engine()

# Enable WAL mode and foreign keys for SQLite
if settings.database_url.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection: Any, _connection_record: Any) -> None:
        """Enable WAL journal mode and foreign key enforcement for SQLite."""
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.close()


SessionLocal: sessionmaker[Session] = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that provides a database session.

    Yields a :class:`~sqlalchemy.orm.Session` and ensures it is closed
    after the request completes, even if an exception occurs.

    Yields:
        A SQLAlchemy session.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
