"""Reusable Pydantic field types and validators.

The most important one: `MinorUnits` rejects float inputs so amounts can never
silently become floats at API/CLI boundaries.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import AfterValidator, BeforeValidator, Field

from finance.core.money import is_valid_iso_currency


def _reject_float_minor(v: object) -> object:
    """Pydantic happily coerces 12.50 → 12 via int(). We don't want that for money.

    Reject any non-bool numeric value that isn't already an int.
    """
    if isinstance(v, bool):
        raise ValueError("amount must be an integer in minor units, not a bool")
    if isinstance(v, float):
        raise ValueError(
            "amount must be an integer in minor units (e.g., pence/cents); "
            "JSON numbers with decimal parts are rejected to avoid float rounding"
        )
    return v


def _ensure_iso_currency(v: str) -> str:
    code = v.upper()
    if not is_valid_iso_currency(code):
        raise ValueError(
            f"currency must be a 3-letter ISO 4217 code, got {v!r}"
        )
    return code


MinorUnits = Annotated[
    int,
    BeforeValidator(_reject_float_minor),
    Field(strict=True, description="Money amount in integer minor units."),
]
"""Strict integer field for money; rejects floats with a helpful message."""


CurrencyCode = Annotated[
    str,
    AfterValidator(_ensure_iso_currency),
    Field(min_length=3, max_length=3, description="ISO 4217 3-letter currency code."),
]
"""Uppercase 3-letter ISO 4217 code; uppercases and validates shape."""
