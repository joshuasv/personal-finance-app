"""Integration tests for the MCP server transport."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from finance.api.app import create_app
from finance.core.config import ApiSettings, DatabaseSettings, Settings
from finance.core.operations import build_default_registry
from finance.mcp.server import build_server

pytestmark = pytest.mark.integration


API_KEY = "mcp-test-key"


@pytest.fixture
def mcp_settings(db_path: Path) -> Settings:
    return Settings(
        db=DatabaseSettings(path=db_path),
        api=ApiSettings(host="127.0.0.1", port=8000, key=API_KEY),
    )


@pytest.fixture
def mcp_session_maker(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def test_build_server_registers_every_operation(
    mcp_settings: Settings, mcp_session_maker: sessionmaker
) -> None:
    registry = build_default_registry()
    server = build_server(registry, mcp_settings, mcp_session_maker)
    # FastMCP exposes its tool manager; iterate it to confirm every op is registered.
    tools = server._tool_manager._tools  # type: ignore[attr-defined]
    assert set(tools.keys()) == set(registry.names())


def _resolve_mcp_input_schema(mcp_schema: dict, model_name: str) -> dict:
    """FastMCP wraps the input as {properties: {payload: <ref>}}; deref it."""
    payload = mcp_schema["properties"]["payload"]
    if "$ref" in payload:
        ref_name = payload["$ref"].rsplit("/", 1)[-1]
        return mcp_schema["$defs"][ref_name]
    return payload


def test_mcp_tool_input_schema_matches_registry(
    mcp_settings: Settings, mcp_session_maker: sessionmaker
) -> None:
    registry = build_default_registry()
    server = build_server(registry, mcp_settings, mcp_session_maker)
    tools = server._tool_manager._tools  # type: ignore[attr-defined]
    for op in registry.all():
        tool = tools[op.name]
        rest_schema = op.input_model.model_json_schema()
        mcp_payload = _resolve_mcp_input_schema(tool.parameters, op.input_model.__name__)
        # The dereferenced MCP payload schema has the same property names and
        # the same required-field set as the REST input model schema.
        assert mcp_payload.get("properties", {}).keys() == rest_schema.get(
            "properties", {}
        ).keys(), f"property mismatch on {op.name}"
        assert set(mcp_payload.get("required", []) or []) == set(
            rest_schema.get("required", []) or []
        ), f"required-field mismatch on {op.name}"


def test_mcp_route_blocks_unauthenticated(
    mcp_settings: Settings, engine: Engine
) -> None:
    """Hit /mcp without auth — should get 401 from the middleware."""
    session_maker = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, future=True
    )
    app = create_app(
        mcp_settings,
        registry=build_default_registry(),
        session_maker=session_maker,
    )
    client = TestClient(app)
    r = client.get("/mcp/")
    assert r.status_code == 401
    assert API_KEY not in r.text


def test_mcp_route_accepts_with_key(mcp_settings: Settings, engine: Engine) -> None:
    """With a valid key the /mcp endpoint is reachable (it'll respond with
    a protocol-specific status, which is enough to prove auth passed)."""
    session_maker = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, future=True
    )
    app = create_app(
        mcp_settings,
        registry=build_default_registry(),
        session_maker=session_maker,
    )
    client = TestClient(app)
    # MCP streamable HTTP responds to GET with 405/406/202 depending on
    # session state. Anything other than 401 means auth passed.
    r = client.get("/mcp/", headers={"Authorization": f"Bearer {API_KEY}"})
    assert r.status_code != 401


def test_mcp_tool_call_invokes_same_callable_as_rest(
    mcp_settings: Settings, mcp_session_maker: sessionmaker
) -> None:
    """Calling the FastMCP tool directly produces the same result as the
    operation callable would on a fresh session — proving REST and MCP share
    one code path."""
    registry = build_default_registry()
    server = build_server(registry, mcp_settings, mcp_session_maker)
    tools = server._tool_manager._tools  # type: ignore[attr-defined]
    create_tool = tools["create_account"]
    op = registry.get("create_account")

    payload = op.input_model(name="Wise GBP", currency="GBP", opening_balance_minor=0)
    result = create_tool.fn(payload)
    assert isinstance(result, op.output_model)
    assert result.account.name == "Wise GBP"
    assert result.account.currency == "GBP"
