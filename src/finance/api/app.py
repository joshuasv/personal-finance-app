"""FastAPI application factory.

Builds the REST surface from the operation registry. The same registry feeds
the MCP server (see `finance.mcp`); everything in `/api/*` is single-source.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker

from finance.api.auth import make_require_api_key
from finance.api.routing import register_operations
from finance.core.config import Settings
from finance.core.db import engine_for, session_factory_for
from finance.core.operations import OperationRegistry, build_default_registry


def create_app(
    settings: Settings | None = None,
    *,
    registry: OperationRegistry | None = None,
    session_maker: sessionmaker[Any] | None = None,
    mount_mcp: bool = True,
) -> FastAPI:
    """Build a FastAPI app wired to the operation registry.

    Defaults are convenient for `finance serve`; tests override the registry
    and session factory to point at an isolated DB. Pass `mount_mcp=False` to
    skip the in-process MCP server (used by tests that target REST only).
    """
    settings = settings or Settings.load()
    registry = registry or build_default_registry()
    if session_maker is None:
        engine = engine_for(settings.db.path)
        session_maker = session_factory_for(engine)

    app = FastAPI(title="finance", version="0.1.0")

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    require_api_key = make_require_api_key(settings)
    register_operations(app, registry, session_maker, auth_dependency=require_api_key)

    if mount_mcp:
        from finance.mcp import build_streamable_http_app

        mcp_app = build_streamable_http_app(registry, settings, session_maker)
        app.mount("/mcp", mcp_app)

    # Stash for tests / introspection.
    app.state.settings = settings
    app.state.registry = registry
    app.state.session_maker = session_maker
    return app
