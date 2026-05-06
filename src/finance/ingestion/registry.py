"""Registry of installed institution adapters."""

from __future__ import annotations

from collections.abc import Iterator

from finance.ingestion.protocols import InstitutionAdapter


class AdapterRegistry:
    def __init__(self) -> None:
        self._by_id: dict[str, InstitutionAdapter] = {}

    def register_adapter(self, adapter: InstitutionAdapter) -> None:
        if adapter.id in self._by_id:
            raise ValueError(f"adapter {adapter.id!r} is already registered")
        self._by_id[adapter.id] = adapter

    def get_adapter(self, adapter_id: str) -> InstitutionAdapter:
        try:
            return self._by_id[adapter_id]
        except KeyError as exc:
            raise KeyError(f"unknown adapter {adapter_id!r}") from exc

    def list_adapters(self) -> list[InstitutionAdapter]:
        return sorted(self._by_id.values(), key=lambda a: a.id)

    def has(self, adapter_id: str) -> bool:
        return adapter_id in self._by_id

    def __iter__(self) -> Iterator[InstitutionAdapter]:
        return iter(self.list_adapters())

    def __len__(self) -> int:
        return len(self._by_id)
