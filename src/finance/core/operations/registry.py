"""Mutable operation registry."""

from __future__ import annotations

from collections.abc import Iterator

from finance.core.operations.operation import Operation


class OperationRegistry:
    def __init__(self) -> None:
        self._ops: dict[str, Operation] = {}

    def register(self, op: Operation) -> None:
        if op.name in self._ops:
            raise ValueError(f"operation {op.name!r} is already registered")
        self._ops[op.name] = op

    def get(self, name: str) -> Operation:
        try:
            return self._ops[name]
        except KeyError as exc:
            raise KeyError(f"no operation named {name!r}") from exc

    def has(self, name: str) -> bool:
        return name in self._ops

    def all(self) -> tuple[Operation, ...]:
        return tuple(self._ops.values())

    def names(self) -> tuple[str, ...]:
        return tuple(self._ops.keys())

    def __iter__(self) -> Iterator[Operation]:
        return iter(self._ops.values())

    def __len__(self) -> int:
        return len(self._ops)
