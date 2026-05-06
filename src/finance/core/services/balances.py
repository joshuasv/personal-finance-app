"""Account balance computation.

Balance = opening_balance + Σ(transaction.amount_minor for that account).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from finance.core.money import Money
from finance.core.repositories.accounts import AccountRepository
from finance.core.repositories.transactions import TransactionRepository
from finance.core.services.accounts import AccountNotFoundError


def account_balance(session: Session, *, account_id: int) -> Money:
    accounts = AccountRepository(session)
    account = accounts.get(account_id)
    if account is None:
        raise AccountNotFoundError(f"no account with id {account_id}")
    txs = TransactionRepository(session)
    total = account.opening_balance_minor + txs.sum_for_account(account_id)
    return Money(minor=total, currency=account.currency)
