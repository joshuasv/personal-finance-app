"""Shared pytest fixtures.

The DB fixture builds a fresh on-disk SQLite under a tmp dir so Alembic
migrations behave the same as in production (an in-memory DB plays poorly
with Alembic's reuse of the connection between commands).
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from finance.core import db as core_db
from finance.core.config import DatabaseSettings, Settings


@pytest.fixture
def finance_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolated runtime dir for tests."""
    home = tmp_path / "finance-home"
    home.mkdir()
    monkeypatch.setenv("FINANCE_HOME", str(home))
    return home


@pytest.fixture
def db_path(finance_home: Path) -> Path:
    return finance_home / "test.db"


@pytest.fixture
def settings(db_path: Path) -> Settings:
    return Settings(db=DatabaseSettings(path=db_path))


@pytest.fixture
def engine(settings: Settings) -> Generator[Engine, None, None]:
    """A function-scoped engine against a fresh on-disk SQLite, fully migrated."""
    core_db.init_db(settings)
    eng = core_db.engine_for(settings.db.path)
    try:
        yield eng
    finally:
        eng.dispose()


@pytest.fixture
def session_factory(engine: Engine) -> sessionmaker[Session]:
    return core_db.session_factory_for(engine)


@pytest.fixture
def db_session(session_factory: sessionmaker[Session]) -> Generator[Session, None, None]:
    """A live session bound to the migrated DB; commits at the end."""
    session = session_factory()
    try:
        yield session
        session.commit()
    finally:
        session.close()
