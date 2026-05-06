"""CRUD for accounts."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from finance.core.models import Account


class AccountRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def add(
        self,
        *,
        name: str,
        currency: str,
        opening_balance_minor: int = 0,
    ) -> Account:
        account = Account(
            name=name,
            currency=currency,
            opening_balance_minor=opening_balance_minor,
        )
        self._s.add(account)
        self._s.flush()
        return account

    def get(self, account_id: int) -> Account | None:
        return self._s.get(Account, account_id)

    def get_by_active_name(self, name: str) -> Account | None:
        stmt = select(Account).where(Account.name == name, Account.archived.is_(False))
        return self._s.scalars(stmt).one_or_none()

    def list_active(self) -> Sequence[Account]:
        stmt = select(Account).where(Account.archived.is_(False)).order_by(Account.name)
        return self._s.scalars(stmt).all()

    def list_all(self) -> Sequence[Account]:
        stmt = select(Account).order_by(Account.name)
        return self._s.scalars(stmt).all()

    def archive(self, account: Account) -> Account:
        account.archived = True
        self._s.flush()
        return account
