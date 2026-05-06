"""Statement ingestion pipeline.

Adapters parse source artifacts; the pipeline writes drafts; the review
functions confirm or reject drafts. `core` does not import this package —
the surface layers wire up the registry at startup.
"""

from finance.ingestion.protocols import (
    AdapterParseError,
    InstitutionAdapter,
    ParsedTransaction,
)
from finance.ingestion.registry import AdapterRegistry
from finance.ingestion.wise_pdf import WiseStatementAdapter


def build_default_adapter_registry() -> AdapterRegistry:
    """Return a fresh registry with all built-in institution adapters."""
    registry = AdapterRegistry()
    registry.register_adapter(WiseStatementAdapter())
    return registry


__all__ = [
    "AdapterParseError",
    "AdapterRegistry",
    "InstitutionAdapter",
    "ParsedTransaction",
    "WiseStatementAdapter",
    "build_default_adapter_registry",
]
