"""
Shared pytest fixtures for the Job Bot test suite.

Provides an in-memory SQLite session fixture that creates all tables
before each test and tears down afterwards.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database.models import Base


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    """Provide an in-memory SQLite database session for testing.

    Creates all tables defined in :class:`~app.database.models.Base`
    before the test runs, and closes the session after the test completes.

    Yields:
        A SQLAlchemy :class:`~sqlalchemy.orm.Session` bound to an
        in-memory SQLite database.
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    session = TestSession()
    yield session
    session.close()
