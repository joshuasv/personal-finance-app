"""Reporting queries: monthly summary, balance snapshot.

These are pure read functions over the canonical ledger. Drafts are excluded
by construction — only `Transaction` rows are considered. Multi-currency is
modelled as one summary block per currency present that month; v1 does not
convert across currencies.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from finance.core.models import Account, Transaction
from finance.core.services.balances import account_balance


@dataclass(frozen=True, slots=True)
class IncomeExpenseSummary:
    """Single-currency summary block for one month."""

    currency: str
    income_minor: int
    expense_minor: int
    net_savings_minor: int
    savings_rate: float | None
    transaction_count: int


@dataclass(frozen=True, slots=True)
class AccountBalance:
    account_id: int
    name: str
    currency: str
    balance_minor: int


@dataclass(frozen=True, slots=True)
class MonthlySummary:
    year: int
    month: int
    start: date
    end: date
    blocks: list[IncomeExpenseSummary]


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def _compute_savings_rate(income_minor: int, net_savings_minor: int) -> float | None:
    if income_minor <= 0:
        return None
    return round((net_savings_minor / income_minor) * 100.0, 2)


def income_expense_for_month(
    session: Session,
    *,
    year: int,
    month: int,
    currency: str,
) -> IncomeExpenseSummary:
    """Income, expense, net savings, savings rate for one (year, month, currency)."""
    iso_currency = currency.upper()
    start, end = _month_bounds(year, month)

    inflow = func.coalesce(
        func.sum(case((Transaction.amount_minor > 0, Transaction.amount_minor), else_=0)),
        0,
    )
    outflow = func.coalesce(
        func.sum(case((Transaction.amount_minor < 0, Transaction.amount_minor), else_=0)),
        0,
    )
    count_expr = func.count(Transaction.id)

    row = session.execute(
        select(inflow, outflow, count_expr)
        .where(Transaction.posted_date >= start)
        .where(Transaction.posted_date <= end)
        .where(Transaction.currency == iso_currency)
    ).one()
    income_minor = int(row[0] or 0)
    outflow_minor = int(row[1] or 0)
    expense_minor = -outflow_minor  # Expense is the absolute value of outflows.
    net = income_minor + outflow_minor  # outflow_minor is negative
    return IncomeExpenseSummary(
        currency=iso_currency,
        income_minor=income_minor,
        expense_minor=expense_minor,
        net_savings_minor=net,
        savings_rate=_compute_savings_rate(income_minor, net),
        transaction_count=int(row[2] or 0),
    )


def account_balance_snapshot(session: Session) -> list[AccountBalance]:
    """Per-account balances for non-archived accounts. No cross-currency total."""
    accounts = (
        session.execute(
            select(Account)
            .where(Account.archived.is_(False))
            .order_by(Account.currency, Account.name)
        )
        .scalars()
        .all()
    )
    out: list[AccountBalance] = []
    for a in accounts:
        money = account_balance(session, account_id=a.id)
        out.append(
            AccountBalance(
                account_id=a.id,
                name=a.name,
                currency=a.currency,
                balance_minor=money.minor,
            )
        )
    return out


def _currencies_present_in_month(
    session: Session, *, year: int, month: int
) -> list[str]:
    start, end = _month_bounds(year, month)
    rows = session.execute(
        select(Transaction.currency)
        .where(Transaction.posted_date >= start)
        .where(Transaction.posted_date <= end)
        .distinct()
        .order_by(Transaction.currency)
    ).all()
    return [r[0] for r in rows]


def monthly_summary(
    session: Session, *, year: int, month: int
) -> MonthlySummary:
    """Calendar-month summary, one block per currency present that month.

    Returns at least one (empty) block in the user's first-account currency
    only when no transactions exist? No — v1 returns an empty `blocks` list on
    a zero-transaction month so the caller can decide how to render it.
    """
    start, end = _month_bounds(year, month)
    blocks: list[IncomeExpenseSummary] = []
    for currency in _currencies_present_in_month(session, year=year, month=month):
        blocks.append(
            income_expense_for_month(
                session, year=year, month=month, currency=currency
            )
        )
    return MonthlySummary(
        year=year, month=month, start=start, end=end, blocks=blocks
    )


__all__ = [
    "AccountBalance",
    "IncomeExpenseSummary",
    "MonthlySummary",
    "account_balance_snapshot",
    "income_expense_for_month",
    "monthly_summary",
]
