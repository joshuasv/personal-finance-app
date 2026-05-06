from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from finance.core import db as core_db
from finance.core.config import DatabaseSettings, Settings
from finance.core.models import Account

pytestmark = pytest.mark.integration


def _settings_for(path: Path) -> Settings:
    return Settings(db=DatabaseSettings(path=path))


def _make_account(name: str) -> Account:
    return Account(name=name, currency="GBP")


def test_init_db_creates_schema(finance_home: Path) -> None:
    db_path = finance_home / "fresh.db"
    settings = _settings_for(db_path)

    result = core_db.init_db(settings)

    assert result["migrations_applied"] is True
    assert result["current_revision"] == "0001_v1_baseline"

    engine = core_db.engine_for(db_path)
    factory = core_db.session_factory_for(engine)
    with factory() as session:
        names = set(session.scalars(select(Account.name)).all())
    assert names == set()


def test_init_db_is_idempotent(finance_home: Path) -> None:
    db_path = finance_home / "again.db"
    settings = _settings_for(db_path)

    first = core_db.init_db(settings)
    second = core_db.init_db(settings)

    assert first["migrations_applied"] is True
    assert second["migrations_applied"] is False
    assert first["current_revision"] == second["current_revision"]


def test_session_scope_commits_on_success(finance_home: Path) -> None:
    db_path = finance_home / "scope.db"
    core_db.init_db(_settings_for(db_path))
    factory = core_db.session_factory_for(core_db.engine_for(db_path))

    with core_db.session_scope(factory) as session:
        session.add(_make_account("freshly-added"))

    with factory() as session:
        names = set(session.scalars(select(Account.name)).all())
    assert "freshly-added" in names


def test_session_scope_rolls_back_on_error(finance_home: Path) -> None:
    db_path = finance_home / "scope-rb.db"
    core_db.init_db(_settings_for(db_path))
    factory = core_db.session_factory_for(core_db.engine_for(db_path))

    with pytest.raises(RuntimeError), core_db.session_scope(factory) as session:
        session.add(_make_account("should-not-persist"))
        raise RuntimeError("boom")

    with factory() as session:
        names = set(session.scalars(select(Account.name)).all())
    assert "should-not-persist" not in names
