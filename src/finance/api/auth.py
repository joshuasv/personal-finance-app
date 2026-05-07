"""API-key authentication: `Authorization: Bearer <key>`, constant-time compare."""

from __future__ import annotations

import hmac
from collections.abc import Awaitable, Callable

from fastapi import Header, HTTPException, status

from finance.core.config import Settings


def _missing(detail: str = "missing api key") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _wrong() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="invalid api key",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _extract_bearer(authorization: str | None) -> str | None:
    if authorization is None:
        return None
    parts = authorization.split(maxsplit=1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    return token or None


def make_require_api_key(settings: Settings) -> Callable[..., Awaitable[None]]:
    """Build a FastAPI dependency that enforces the API key on the given settings.

    The dependency raises 401 with body `{"detail": "..."}` on missing/invalid
    keys. We intentionally do NOT include the supplied key in any error
    message, log line, or response body.
    """
    expected = settings.api.key

    async def require_api_key(
        authorization: str | None = Header(default=None, alias="Authorization"),
    ) -> None:
        if expected is None or expected == "":
            # The server has no API key configured. Fail closed.
            raise _missing("api key not configured on server")
        token = _extract_bearer(authorization)
        if token is None:
            raise _missing()
        if not hmac.compare_digest(token, expected):
            raise _wrong()

    return require_api_key
