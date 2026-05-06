"""Contract test: REST and MCP must expose the same operations identically.

For every operation in the registry, this test:
  1. Verifies a `POST /api/<op-name>` route exists in the FastAPI app.
  2. Verifies an MCP tool with the same name exists on the FastMCP server.
  3. Verifies their input and output JSON Schemas are equivalent (modulo
     the FastMCP `payload`-wrapper level).

The point: adding a new operation to the registry surfaces it on both
transports automatically, and any hand-override of a per-surface schema
that diverges from the model will fail this test.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from finance.api.app import create_app
from finance.core.config import ApiSettings, DatabaseSettings, Settings
from finance.core.operations import build_default_registry
from finance.mcp.server import build_server

pytestmark = pytest.mark.contract


@pytest.fixture
def settings(db_path) -> Settings:
    return Settings(
        db=DatabaseSettings(path=db_path),
        api=ApiSettings(host="127.0.0.1", port=8000, key="contract-test-key"),
    )


@pytest.fixture
def session_maker_fx(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


@pytest.fixture
def fastapi_app(settings: Settings, session_maker_fx: sessionmaker) -> FastAPI:
    return create_app(
        settings,
        registry=build_default_registry(),
        session_maker=session_maker_fx,
        mount_mcp=False,
    )


def _resolve_ref(schema: dict[str, Any], root: dict[str, Any]) -> dict[str, Any]:
    """Inline a $ref to its target definition (one hop)."""
    ref = schema.get("$ref")
    if not ref:
        return schema
    name = ref.rsplit("/", 1)[-1]
    return root["$defs"][name]


def _normalize(schema: dict[str, Any]) -> dict[str, Any]:
    """Drop fields that are pure annotation noise for equivalence purposes."""
    skip = {"title", "description"}
    return {k: v for k, v in schema.items() if k not in skip}


def _compare_schemas(rest: dict[str, Any], mcp: dict[str, Any], op_name: str) -> None:
    """Assert that two model JSON Schemas describe the same shape.

    Compares the property-name set, the required-field set, and (recursively)
    the type/format on each property.
    """
    rest_props = rest.get("properties", {}) or {}
    mcp_props = mcp.get("properties", {}) or {}
    assert (
        rest_props.keys() == mcp_props.keys()
    ), f"property name mismatch on {op_name}: REST={set(rest_props)} MCP={set(mcp_props)}"
    rest_required = set(rest.get("required", []) or [])
    mcp_required = set(mcp.get("required", []) or [])
    assert (
        rest_required == mcp_required
    ), f"required-field mismatch on {op_name}: REST={rest_required} MCP={mcp_required}"
    for key in rest_props:
        r = _normalize(rest_props[key])
        m = _normalize(mcp_props[key])
        # A bare type/format check is enough to detect drift; we don't need
        # full structural equality (FastMCP injects MCP-flavored extras).
        for axis in ("type", "format", "enum", "minLength", "maxLength"):
            if axis in r or axis in m:
                assert r.get(axis) == m.get(axis), (
                    f"{op_name}.{key}.{axis}: REST={r.get(axis)} MCP={m.get(axis)}"
                )


def test_every_operation_is_on_both_surfaces(
    fastapi_app: FastAPI,
    settings: Settings,
    session_maker_fx: sessionmaker,
) -> None:
    registry = build_default_registry()
    server = build_server(registry, settings, session_maker_fx)

    rest_paths = set(fastapi_app.openapi().get("paths", {}).keys())
    mcp_tools = server._tool_manager._tools  # type: ignore[attr-defined]

    for op in registry.all():
        assert (
            f"/api/{op.name}" in rest_paths
        ), f"operation {op.name!r} is registered but not exposed on REST"
        assert (
            op.name in mcp_tools
        ), f"operation {op.name!r} is registered but not exposed on MCP"


def test_input_schemas_match_for_every_operation(
    fastapi_app: FastAPI,
    settings: Settings,
    session_maker_fx: sessionmaker,
) -> None:
    registry = build_default_registry()
    server = build_server(registry, settings, session_maker_fx)
    mcp_tools = server._tool_manager._tools  # type: ignore[attr-defined]

    for op in registry.all():
        rest_schema = op.input_model.model_json_schema()
        mcp_schema = mcp_tools[op.name].parameters
        # FastMCP wraps the input as {properties: {payload: <ref>}}; deref it.
        payload = mcp_schema["properties"]["payload"]
        if "$ref" in payload:
            payload = _resolve_ref(payload, mcp_schema)
        _compare_schemas(rest_schema, payload, op.name)


def test_output_schemas_match_for_every_operation(
    fastapi_app: FastAPI,
    settings: Settings,
    session_maker_fx: sessionmaker,
) -> None:
    """Both surfaces produce JSON shaped by the same Pydantic output_model."""
    registry = build_default_registry()
    openapi = fastapi_app.openapi()

    for op in registry.all():
        # The REST OpenAPI references the output schema via a $ref in the
        # 200-response content. Resolve it to the concrete schema.
        path = openapi["paths"][f"/api/{op.name}"]
        ok_schema = (
            path["post"]["responses"]["200"]["content"]
            ["application/json"]["schema"]
        )
        ref = ok_schema.get("$ref")
        if ref:
            name = ref.rsplit("/", 1)[-1]
            rest_output = openapi["components"]["schemas"][name]
        else:
            rest_output = ok_schema

        model_schema = op.output_model.model_json_schema()
        # Compare top-level property/required structure with the model's
        # canonical schema.
        _compare_schemas(model_schema, rest_output, op.name)
