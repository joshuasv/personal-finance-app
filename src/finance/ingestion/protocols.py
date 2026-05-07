"""Adapter protocol every institution-specific parser implements.

An adapter consumes one source artifact (PDF, CSV, etc.) and yields parsed
transaction lines. The pipeline (not the adapter) creates the IngestionBatch
and turns each parsed line into a DraftTransaction row.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class ParsedTransaction:
    """One transaction line extracted by an adapter, pre-persistence."""

    posted_date: date
    amount_minor: int
    currency: str
    payee: str
    memo: str | None = None


class AdapterParseError(Exception):
    """Raised by an adapter when a source artifact cannot be parsed.

    Should name the adapter and (where possible) the page or section that
    broke parsing.
    """

    def __init__(self, adapter_id: str, message: str, *, page: int | None = None):
        self.adapter_id = adapter_id
        self.page = page
        location = f" page {page}" if page is not None else ""
        super().__init__(f"[{adapter_id}{location}] {message}")


@runtime_checkable
class InstitutionAdapter(Protocol):
    """Interface every institution adapter implements.

    Implementations are structurally typed; they need not inherit from this
    Protocol. The pipeline uses these attributes to populate `IngestionBatch`
    metadata and to display the adapter in pickers.
    """

    id: str
    display_name: str
    source_artifact_type: str

    def parse(self, path: Path) -> Iterable[ParsedTransaction]: ...
