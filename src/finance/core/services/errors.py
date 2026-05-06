"""Domain errors raised by services.

The operation/registry layer maps these to API/CLI errors. Surfaces SHALL NOT
catch SQLAlchemy errors directly — all expected failure modes are typed here.
"""

from __future__ import annotations


class DomainError(Exception):
    """Base class for all expected domain failures."""


class ValidationError(DomainError):
    """Caller supplied an invalid value (currency, amount, etc.)."""


class NotFoundError(DomainError):
    """Caller referenced an entity that does not exist."""


class CurrencyMismatchError(ValidationError):
    """Transaction currency does not match its account."""


class AmountZeroError(ValidationError):
    """Transaction amount must be non-zero."""


class AccountArchivedError(ValidationError):
    """Operation refused because the account is archived."""
