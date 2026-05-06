"""Transaction services: invariants on top of `TransactionRepository`."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import date

from sqlalchemy.orm import Session

from finance.core.models import Account, Transaction
from finance.core.repositories.accounts import AccountRepository
from finance.core.repositories.transactions import TransactionRepository
from finance.core.services.accounts import AccountNotFoundError
from finance.core.services.errors import (
    AccountArchivedError,
    AmountZeroError,
    CurrencyMismatchError,
    NotFoundError,
    ValidationError,
)


class TransactionNotFoundError(NotFoundError):
    pass


class DuplicateTransactionError(ValidationError):
    """A transaction with the same content hash already exists for the account."""


def compute_content_hash(
    *,
    account_id: int,
    posted_date: date,
    amount_minor: int,
    currency: str,
    payee: str,
    memo: str | None,
) -> str:
    """Stable hash of the user-facing transaction fields, for de-duplication.

    The same payload (account, date, amount, currency, payee, memo) collapses
    to the same hash, so the unique constraint `(account_id, content_hash)`
    catches both manual duplicates and re-imports.
    """
    parts = [
        str(account_id),
        posted_date.isoformat(),
        str(amount_minor),
        currency.upper(),
        payee.strip(),
        (memo or "").strip(),
    ]
    h = hashlib.sha256()
    h.update("\x1f".join(parts).encode("utf-8"))
    return h.hexdigest()


def _resolve_account(session: Session, account_id: int) -> Account:
    account = AccountRepository(session).get(account_id)
    if account is None:
        raise AccountNotFoundError(f"no account with id {account_id}")
    return account


def _validate_payee(payee: str) -> str:
    cleaned = payee.strip()
    if not cleaned:
        raise ValidationError("payee must not be empty")
    return cleaned


def record_transaction(
    session: Session,
    *,
    account_id: int,
    posted_date: date,
    amount_minor: int,
    currency: str,
    payee: str,
    entered_by: str = "manual",
    memo: str | None = None,
) -> Transaction:
    """Insert a transaction. Enforces currency, non-zero amount, unique hash."""
    account = _resolve_account(session, account_id)
    if account.archived:
        raise AccountArchivedError(
            f"account {account.name!r} is archived and cannot accept transactions"
        )
    iso_currency = currency.strip().upper()
    if iso_currency != account.currency:
        raise CurrencyMismatchError(
            f"transaction currency {iso_currency!r} does not match account "
            f"{account.name!r} ({account.currency})"
        )
    if amount_minor == 0:
        raise AmountZeroError("transaction amount must not be zero")
    payee_clean = _validate_payee(payee)

    content_hash = compute_content_hash(
        account_id=account_id,
        posted_date=posted_date,
        amount_minor=amount_minor,
        currency=iso_currency,
        payee=payee_clean,
        memo=memo,
    )
    repo = TransactionRepository(session)
    if repo.find_by_account_and_hash(account_id, content_hash) is not None:
        raise DuplicateTransactionError(
            "a transaction with the same date/amount/payee already exists "
            "for this account"
        )
    return repo.add(
        account_id=account_id,
        posted_date=posted_date,
        amount_minor=amount_minor,
        currency=iso_currency,
        payee=payee_clean,
        entered_by=entered_by,
        content_hash=content_hash,
        memo=memo,
    )


def update_transaction(
    session: Session,
    *,
    transaction_id: int,
    posted_date: date | None = None,
    amount_minor: int | None = None,
    payee: str | None = None,
    memo: str | None = None,
) -> Transaction:
    """Mutate user-editable fields on an existing transaction.

    Currency and account are immutable through this surface — to change them,
    delete and re-record.
    """
    repo = TransactionRepository(session)
    tx = repo.get(transaction_id)
    if tx is None:
        raise TransactionNotFoundError(f"no transaction with id {transaction_id}")

    new_date = posted_date if posted_date is not None else tx.posted_date
    new_amount = amount_minor if amount_minor is not None else tx.amount_minor
    new_payee = _validate_payee(payee) if payee is not None else tx.payee
    new_memo = memo if memo is not None else tx.memo

    if new_amount == 0:
        raise AmountZeroError("transaction amount must not be zero")

    new_hash = compute_content_hash(
        account_id=tx.account_id,
        posted_date=new_date,
        amount_minor=new_amount,
        currency=tx.currency,
        payee=new_payee,
        memo=new_memo,
    )
    if new_hash != tx.content_hash:
        clash = repo.find_by_account_and_hash(tx.account_id, new_hash)
        if clash is not None and clash.id != tx.id:
            raise DuplicateTransactionError(
                "another transaction on this account has the same "
                "date/amount/payee"
            )

    tx.posted_date = new_date
    tx.amount_minor = new_amount
    tx.payee = new_payee
    tx.memo = new_memo
    tx.content_hash = new_hash
    session.flush()
    return tx


def delete_transaction(session: Session, *, transaction_id: int) -> None:
    repo = TransactionRepository(session)
    tx = repo.get(transaction_id)
    if tx is None:
        raise TransactionNotFoundError(f"no transaction with id {transaction_id}")
    repo.delete(tx)


def list_transactions(
    session: Session,
    *,
    account_id: int,
    start: date | None = None,
    end: date | None = None,
) -> Sequence[Transaction]:
    _resolve_account(session, account_id)
    return TransactionRepository(session).list_for_account(
        account_id, start=start, end=end
    )
