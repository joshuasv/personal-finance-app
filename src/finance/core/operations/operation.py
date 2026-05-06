"""The `Operation` value type."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel
from sqlalchemy.orm import Session


@dataclass(frozen=True, slots=True)
class Operation:
    """One registered domain operation.

    `callable` takes a SQLAlchemy session plus a validated input model and
    returns an output model. Transports build their own surface (REST route,
    MCP tool, CLI command) by walking the registry.
    """

    name: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    callable: Callable[[Session, Any], BaseModel]
    description: str
    tags: tuple[str, ...] = field(default_factory=tuple)
