"""Walk the operation registry and mount each as `POST /api/<op-name>`.

Surfaces never define operations independently — adding one to the registry
makes it appear here automatically. The same Pydantic input/output models
back the OpenAPI schema and the MCP tool schema (see `mcp.server`).
"""

# Deliberately not using `from __future__ import annotations` — FastAPI's
# dependency introspection needs the dynamic op.input_model annotation to be
# evaluated at function-definition time, not lazily as a string.

from collections.abc import Callable
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

from finance.core.operations import Operation, OperationRegistry
from finance.core.services.accounts import (
    AccountInUseError,
    AccountNotFoundError,
    DuplicateAccountNameError,
)
from finance.core.services.errors import (
    DomainError,
    NotFoundError,
    ValidationError,
)
from finance.core.services.transactions import (
    DuplicateTransactionError,
    TransactionNotFoundError,
)
from finance.ingestion.pipeline import DuplicateBatchError
from finance.ingestion.protocols import AdapterParseError
from finance.ingestion.review import DraftNotFoundError, DraftNotPendingError


def _http_status_for_domain_error(exc: DomainError) -> int:
    if isinstance(
        exc,
        (
            DuplicateAccountNameError,
            DuplicateTransactionError,
            DuplicateBatchError,
            AccountInUseError,
        ),
    ):
        return status.HTTP_409_CONFLICT
    if isinstance(
        exc,
        (
            AccountNotFoundError,
            TransactionNotFoundError,
            DraftNotFoundError,
        ),
    ):
        return status.HTTP_404_NOT_FOUND
    if isinstance(exc, (ValidationError, NotFoundError, DraftNotPendingError)):
        # ValidationError-derived errors that aren't "duplicate" go to 400.
        return status.HTTP_400_BAD_REQUEST
    return status.HTTP_400_BAD_REQUEST


def _make_handler(
    op: Operation,
    session_maker: sessionmaker[Session],
) -> Callable[..., Any]:
    """Build the FastAPI route handler for one operation.

    The closure captures the operation and the session factory; per-request a
    fresh session is opened and committed/rolled-back around the call.
    """

    async def handler(payload: op.input_model) -> BaseModel:  # type: ignore[name-defined]
        session = session_maker()
        try:
            try:
                result = op.callable(session, payload)
            except (DomainError, AdapterParseError) as exc:
                session.rollback()
                if isinstance(exc, AdapterParseError):
                    # Parser failures map to 400 — bad input artifact.
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=str(exc),
                    ) from exc
                raise HTTPException(
                    status_code=_http_status_for_domain_error(exc),
                    detail=str(exc),
                ) from exc
            session.commit()
            return result
        except HTTPException:
            raise
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    handler.__name__ = f"{op.name}_handler"
    handler.__doc__ = op.description
    return handler


def register_operations(
    app: FastAPI,
    registry: OperationRegistry,
    session_maker: sessionmaker[Session],
    auth_dependency: Callable[..., Any] | None = None,
) -> None:
    """Mount every operation in `registry` as `POST /api/<op-name>`.

    `auth_dependency` is a FastAPI `Depends`-compatible callable; if supplied,
    it's attached to every operation route (unauthenticated routes like
    `/health` are mounted separately).
    """
    deps = [Depends(auth_dependency)] if auth_dependency is not None else []
    for op in registry.all():
        handler = _make_handler(op, session_maker)
        app.add_api_route(
            f"/api/{op.name}",
            handler,
            methods=["POST"],
            response_model=op.output_model,
            tags=list(op.tags) or ["operations"],
            description=op.description,
            name=op.name,
            dependencies=deps,
        )
