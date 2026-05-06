"""Account services: invariants on top of `AccountRepository`."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from finance.core.models import Account, Transaction
from finance.core.money import is_valid_iso_currency
from finance.core.repositories.accounts import AccountRepository
from finance.core.services.errors import (
    NotFoundError,
    ValidationError,
)


class AccountNotFoundError(NotFoundError):
    pass


class DuplicateAccountNameError(ValidationError):
    pass


class AccountInUseError(ValidationError):
    """Refusing to archive an account that still has transactions."""


def _normalize_name(name: str) -> str:
    cleaned = name.strip()
    if not cleaned:
        raise ValidationError("account name must not be empty")
    return cleaned


def _normalize_currency(currency: str) -> str:
    code = currency.strip().upper()
    if not is_valid_iso_currency(code):
        raise ValidationError(
            f"currency must be a 3-letter ISO 4217 code, got {currency!r}"
        )
    return code


def create_account(
    session: Session,
    *,
    name: str,
    currency: str,
    opening_balance_minor: int = 0,
) -> Account:
    """Create a new active account. Active names must be unique."""
    name = _normalize_name(name)
    iso_currency = _normalize_currency(currency)

    repo = AccountRepository(session)
    if repo.get_by_active_name(name) is not None:
        raise DuplicateAccountNameError(
            f"an active account named {name!r} already exists"
        )
    return repo.add(
        name=name,
        currency=iso_currency,
        opening_balance_minor=opening_balance_minor,
    )


def archive_account(session: Session, *, account_id: int) -> Account:
    """Soft-delete an account. Refuses if any transaction references it."""
    repo = AccountRepository(session)
    account = repo.get(account_id)
    if account is None:
        raise AccountNotFoundError(f"no account with id {account_id}")
    if account.archived:
        return account
    has_tx = session.scalar(
        select(Transaction.id).where(Transaction.account_id == account_id).limit(1)
    )
    if has_tx is not None:
        raise AccountInUseError(
            f"account {account.name!r} has transactions and cannot be archived"
        )
    return repo.archive(account)


def list_accounts(
    session: Session, *, include_archived: bool = False
) -> Sequence[Account]:
    repo = AccountRepository(session)
    return repo.list_all() if include_archived else repo.list_active()
