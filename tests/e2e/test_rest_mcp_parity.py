"""End-to-end parity test: drive the same flow via REST and via MCP.

Both surfaces share the operation registry, so the same payload should produce
the same outcome on either side. This is the structural guarantee called out
in the spec: REST and MCP cannot drift in the operations they expose or in
the callable they invoke.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from finance.api.app import create_app
from finance.core.config import ApiSettings, DatabaseSettings, Settings
from finance.core.operations import build_default_registry
from finance.mcp.server import build_server

pytestmark = [pytest.mark.e2e, pytest.mark.integration]

API_KEY = "e2e-parity-key"


@pytest.fixture
def parity_settings(db_path: Path) -> Settings:
    return Settings(
        db=DatabaseSettings(path=db_path),
        api=ApiSettings(host="127.0.0.1", port=8000, key=API_KEY),
    )


def test_rest_and_mcp_share_callables(
    parity_settings: Settings, engine: Engine
) -> None:
    sm = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    registry = build_default_registry()
    app = create_app(parity_settings, registry=registry, session_maker=sm)
    client = TestClient(app)
    server = build_server(registry, parity_settings, sm)
    tools = server._tool_manager._tools  # type: ignore[attr-defined]

    # 1. Create an account through REST.
    rest_create = client.post(
        "/api/create_account",
        json={"name": "Parity GBP", "currency": "GBP", "opening_balance_minor": 1000},
        headers={"Authorization": f"Bearer {API_KEY}"},
    )
    assert rest_create.status_code == 200, rest_create.text
    rest_account_id = rest_create.json()["account"]["id"]

    # 2. Look the same account up via the MCP tool callable.
    list_op = registry.get("list_accounts")
    list_tool = tools["list_accounts"]
    payload = list_op.input_model(include_archived=False)
    out = list_tool.fn(payload)
    names = [a.name for a in out.accounts]
    assert "Parity GBP" in names, names

    # 3. Record a transaction via the MCP tool callable.
    record_op = registry.get("record_transaction")
    record_tool = tools["record_transaction"]
    record_payload = record_op.input_model(
        account_id=rest_account_id,
        posted_date="2026-05-01",
        amount_minor=300_000,
        currency="GBP",
        payee="Salary",
    )
    record_result = record_tool.fn(record_payload)
    assert record_result.transaction.payee == "Salary"

    # 4. Read it back via REST and confirm parity.
    rest_list = client.post(
        "/api/list_transactions",
        json={"account_id": rest_account_id, "start": None, "end": None},
        headers={"Authorization": f"Bearer {API_KEY}"},
    )
    assert rest_list.status_code == 200, rest_list.text
    payees = [t["payee"] for t in rest_list.json()["transactions"]]
    assert "Salary" in payees, payees


def test_registry_names_match_across_surfaces(
    parity_settings: Settings, engine: Engine
) -> None:
    sm = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    registry = build_default_registry()
    app = create_app(parity_settings, registry=registry, session_maker=sm)
    client = TestClient(app)
    server = build_server(registry, parity_settings, sm)

    rest_paths = {
        p[len("/api/"):]
        for p in client.get("/openapi.json").json()["paths"]
        if p.startswith("/api/")
    }
    mcp_names = set(server._tool_manager._tools.keys())  # type: ignore[attr-defined]
    registry_names = set(registry.names())
    assert rest_paths == registry_names == mcp_names
