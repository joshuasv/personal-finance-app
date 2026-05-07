"""MCP server: register every operation as an MCP tool.

The server walks the same `OperationRegistry` the REST surface uses, so the
two surfaces cannot drift in what they expose. Each operation becomes one
tool whose JSON Schema is derived from its Pydantic input model.

Auth: the streamable HTTP transport is wrapped in an ASGI middleware that
requires the same `Authorization: Bearer <api-key>` header as REST.
"""

from __future__ import annotations

import hmac
from collections.abc import Callable
from typing import Any

from mcp.server.fastmcp import FastMCP
from sqlalchemy.orm import Session, sessionmaker
from starlette.types import ASGIApp, Receive, Scope, Send

from finance.core.config import Settings
from finance.core.operations import Operation, OperationRegistry


def _make_tool(op: Operation, session_maker: sessionmaker[Session]) -> Callable[..., Any]:
    """Build a tool function whose annotations match the operation's IO models."""
    InputModel = op.input_model
    OutputModel = op.output_model

    def tool(payload: InputModel) -> OutputModel:  # type: ignore[valid-type]
        session = session_maker()
        try:
            result = op.callable(session, payload)
            session.commit()
            return result
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    tool.__name__ = op.name
    tool.__doc__ = op.description
    tool.__annotations__ = {"payload": InputModel, "return": OutputModel}
    return tool


def build_server(
    registry: OperationRegistry,
    settings: Settings,
    session_maker: sessionmaker[Session],
    *,
    name: str = "finance",
) -> FastMCP:
    """Build a FastMCP server that exposes every operation in `registry`."""
    server = FastMCP(name=name, instructions="Personal finance operations.")
    for op in registry.all():
        server.add_tool(
            _make_tool(op, session_maker),
            name=op.name,
            description=op.description,
        )
    # Stash for tests.
    server._finance_settings = settings  # type: ignore[attr-defined]
    server._finance_registry = registry  # type: ignore[attr-defined]
    return server


def auth_middleware_factory(
    expected_key: str | None,
) -> Callable[[ASGIApp], ASGIApp]:
    """Return an ASGI middleware factory that enforces the API key.

    A missing or wrong key results in a 401 JSON response BEFORE the inner
    app sees the request — so unauthenticated clients can neither list nor
    call tools.
    """

    def factory(app: ASGIApp) -> ASGIApp:
        async def middleware(scope: Scope, receive: Receive, send: Send) -> None:
            if scope["type"] != "http":
                await app(scope, receive, send)
                return
            if expected_key is None or expected_key == "":
                await _send_json(send, 401, {"detail": "api key not configured"})
                return
            headers = dict(scope.get("headers") or [])
            auth = headers.get(b"authorization", b"").decode("latin-1")
            parts = auth.split(maxsplit=1)
            token: str | None = None
            if len(parts) == 2 and parts[0].lower() == "bearer":
                token = parts[1].strip() or None
            if token is None:
                await _send_json(send, 401, {"detail": "missing api key"})
                return
            if not hmac.compare_digest(token, expected_key):
                await _send_json(send, 401, {"detail": "invalid api key"})
                return
            await app(scope, receive, send)

        return middleware

    return factory


async def _send_json(send: Send, status_code: int, body: dict[str, Any]) -> None:
    import json

    payload = json.dumps(body).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status_code,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(payload)).encode("ascii")),
                (b"www-authenticate", b"Bearer"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": payload, "more_body": False})


def build_streamable_http_app(
    registry: OperationRegistry,
    settings: Settings,
    session_maker: sessionmaker[Session],
) -> ASGIApp:
    """Construct the ASGI app for the MCP streamable-HTTP transport, with auth."""
    server = build_server(registry, settings, session_maker)
    inner = server.streamable_http_app()
    middleware = auth_middleware_factory(settings.api.key)
    return middleware(inner)


__all__ = [
    "auth_middleware_factory",
    "build_server",
    "build_streamable_http_app",
]
