"""CRUD for transactions."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from finance.core.models import Transaction


class TransactionRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def add(
        self,
        *,
        account_id: int,
        posted_date: date,
        amount_minor: int,
        currency: str,
        payee: str,
        entered_by: str,
        content_hash: str,
        memo: str | None = None,
    ) -> Transaction:
        tx = Transaction(
            account_id=account_id,
            posted_date=posted_date,
            amount_minor=amount_minor,
            currency=currency,
            payee=payee,
            memo=memo,
            entered_by=entered_by,
            content_hash=content_hash,
        )
        self._s.add(tx)
        self._s.flush()
        return tx

    def get(self, transaction_id: int) -> Transaction | None:
        return self._s.get(Transaction, transaction_id)

    def delete(self, tx: Transaction) -> None:
        self._s.delete(tx)
        self._s.flush()

    def find_by_account_and_hash(self, account_id: int, content_hash: str) -> Transaction | None:
        stmt = select(Transaction).where(
            Transaction.account_id == account_id,
            Transaction.content_hash == content_hash,
        )
        return self._s.scalars(stmt).one_or_none()

    def list_for_account(
        self,
        account_id: int,
        *,
        start: date | None = None,
        end: date | None = None,
    ) -> Sequence[Transaction]:
        stmt = select(Transaction).where(Transaction.account_id == account_id)
        if start is not None:
            stmt = stmt.where(Transaction.posted_date >= start)
        if end is not None:
            stmt = stmt.where(Transaction.posted_date <= end)
        stmt = stmt.order_by(Transaction.posted_date, Transaction.id)
        return self._s.scalars(stmt).all()

    def sum_for_account(self, account_id: int) -> int:
        stmt = select(func.coalesce(func.sum(Transaction.amount_minor), 0)).where(
            Transaction.account_id == account_id
        )
        return int(self._s.scalar(stmt) or 0)
