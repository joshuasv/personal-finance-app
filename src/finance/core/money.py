"""Money type stored as integer minor units + 3-letter ISO currency code.

Floats are NEVER used for money at any persistence or API boundary; that
invariant is enforced in `core.validators`. This module just provides a
small immutable container plus format/parse helpers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Currency codes whose minor unit is 0 places (no decimal portion).
_ZERO_DECIMAL = frozenset({"JPY", "KRW", "VND", "CLP", "ISK"})
# Currency codes whose minor unit is 3 places (rare but real).
_THREE_DECIMAL = frozenset({"BHD", "JOD", "KWD", "OMR", "TND"})


def decimals_for(currency: str) -> int:
    """How many decimal places the given currency uses for its minor unit."""
    code = currency.upper()
    if code in _ZERO_DECIMAL:
        return 0
    if code in _THREE_DECIMAL:
        return 3
    return 2


_ISO_CODE_RE = re.compile(r"^[A-Z]{3}$")


def is_valid_iso_currency(code: str) -> bool:
    """Cheap check: ISO 4217 codes are exactly three uppercase letters."""
    return bool(_ISO_CODE_RE.match(code))


@dataclass(frozen=True, slots=True)
class Money:
    minor: int
    currency: str

    def __post_init__(self) -> None:
        if not isinstance(self.minor, int) or isinstance(self.minor, bool):
            raise TypeError("Money.minor must be an int")
        if not isinstance(self.currency, str) or not is_valid_iso_currency(self.currency):
            raise ValueError(f"invalid ISO currency code: {self.currency!r}")

    def format(self) -> str:
        """Render as a human-readable string (e.g., '12.50 GBP', '-3 JPY')."""
        d = decimals_for(self.currency)
        if d == 0:
            return f"{self.minor} {self.currency}"
        sign = "-" if self.minor < 0 else ""
        magnitude = abs(self.minor)
        major, minor = divmod(magnitude, 10**d)
        return f"{sign}{major}.{minor:0{d}d} {self.currency}"

    @classmethod
    def parse(cls, text: str) -> Money:
        """Parse a string like '12.50 GBP' or '-3 JPY' into Money."""
        parts = text.strip().split()
        if len(parts) != 2:
            raise ValueError(f"expected '<amount> <currency>', got {text!r}")
        amount_str, currency = parts
        currency = currency.upper()
        if not is_valid_iso_currency(currency):
            raise ValueError(f"invalid ISO currency code: {currency!r}")
        d = decimals_for(currency)
        sign = -1 if amount_str.startswith("-") else 1
        body = amount_str.lstrip("+-")
        if d == 0:
            if "." in body:
                raise ValueError(f"{currency} has no decimal places; got {amount_str!r}")
            return cls(sign * int(body), currency)
        if "." not in body:
            major_part, minor_part = body, "0" * d
        else:
            major_part, minor_part = body.split(".", 1)
            if len(minor_part) > d:
                raise ValueError(
                    f"{currency} expects at most {d} decimal places; got {amount_str!r}"
                )
            minor_part = minor_part.ljust(d, "0")
        if not major_part.isdigit() or not minor_part.isdigit():
            raise ValueError(f"unparseable amount {amount_str!r}")
        return cls(sign * (int(major_part) * 10**d + int(minor_part)), currency)
