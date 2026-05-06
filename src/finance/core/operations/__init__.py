"""Operation registry: one definition, multiple transports.

Every callable users invoke through REST, MCP, CLI, or Telegram is registered
here as an `Operation`. Surfaces walk the registry and mount each operation
in their own idiom; nobody writes per-surface schemas by hand.
"""

from finance.core.operations.bootstrap import build_default_registry, register_all
from finance.core.operations.operation import Operation
from finance.core.operations.registry import OperationRegistry

__all__ = [
    "Operation",
    "OperationRegistry",
    "build_default_registry",
    "register_all",
]
