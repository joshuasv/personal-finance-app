"""MCP server: same operations as REST, exposed as MCP tools."""

from finance.mcp.server import (
    auth_middleware_factory,
    build_server,
    build_streamable_http_app,
)

__all__ = [
    "auth_middleware_factory",
    "build_server",
    "build_streamable_http_app",
]
