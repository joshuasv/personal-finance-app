"""Database engine, session, and init helpers."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from finance.core.config import Settings

if TYPE_CHECKING:
    from alembic.config import Config
    from sqlalchemy.engine.interfaces import DBAPIConnection


def _enable_sqlite_pragmas(dbapi_connection: DBAPIConnection, _record: object) -> None:
    """SQLite needs PRAGMAs set on every connection: WAL + foreign keys."""
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA synchronous=NORMAL")
    finally:
        cursor.close()


def engine_for(path: Path | str) -> Engine:
    """Build a SQLAlchemy engine for the given SQLite file path.

    Pass `:memory:` for an in-memory DB (useful in tests).
    """
    if str(path) == ":memory:":
        url = "sqlite:///:memory:"
    else:
        path = Path(path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        url = f"sqlite:///{path}"
    engine = create_engine(url, future=True)
    event.listen(engine, "connect", _enable_sqlite_pragmas)
    return engine


def session_factory_for(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Generator[Session, None, None]:
    """Open a session, commit on success, rollback on error, close always."""
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db(settings: Settings | None = None) -> dict[str, object]:
    """Create the DB file (if needed) and run migrations to head.

    Idempotent: re-running on an up-to-date DB applies nothing. Returns a small
    dict describing what happened.
    """
    from alembic import command
    from alembic.runtime.migration import MigrationContext

    settings = settings or Settings.load()
    db_path = settings.db.path
    if str(db_path) != ":memory:":
        Path(db_path).expanduser().parent.mkdir(parents=True, exist_ok=True)

    engine = engine_for(db_path)
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        before_rev = ctx.get_current_revision()

    alembic_cfg = _alembic_config(db_path)
    command.upgrade(alembic_cfg, "head")

    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        after_rev = ctx.get_current_revision()

    return {
        "db_path": str(db_path),
        "previous_revision": before_rev,
        "current_revision": after_rev,
        "migrations_applied": before_rev != after_rev,
    }


def _alembic_config(db_path: Path | str) -> Config:
    from alembic.config import Config as _Config

    cfg = _Config()
    cfg.set_main_option("script_location", "finance.core.migrations:.")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg
