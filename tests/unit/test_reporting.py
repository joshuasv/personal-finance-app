"""Tests for the reporting capability."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.orm import Session

from finance.core.models import DraftStatus, DraftTransaction, IngestionBatch
from finance.core.services import create_account, record_transaction
from finance.reporting.queries import (
    account_balance_snapshot,
    income_expense_for_month,
    monthly_summary,
)

pytestmark = pytest.mark.integration


def _add_tx(
    session: Session,
    *,
    account_id: int,
    posted: date,
    amount_minor: int,
    currency: str,
    payee: str,
):
    return record_transaction(
        session,
        account_id=account_id,
        posted_date=posted,
        amount_minor=amount_minor,
        currency=currency,
        payee=payee,
    )


def test_empty_month_returns_zeros(db_session: Session) -> None:
    create_account(db_session, name="Wise GBP", currency="GBP")
    block = income_expense_for_month(db_session, year=2026, month=5, currency="GBP")
    assert block.income_minor == 0
    assert block.expense_minor == 0
    assert block.net_savings_minor == 0
    assert block.savings_rate is None
    assert block.transaction_count == 0


def test_mixed_inflows_and_outflows_compute_savings_rate(db_session: Session) -> None:
    a = create_account(db_session, name="Wise GBP", currency="GBP")
    _add_tx(
        db_session,
        account_id=a.id,
        posted=date(2026, 5, 5),
        amount_minor=300000,
        currency="GBP",
        payee="Salary",
    )
    _add_tx(
        db_session,
        account_id=a.id,
        posted=date(2026, 5, 10),
        amount_minor=-180000,
        currency="GBP",
        payee="Groceries",
    )
    block = income_expense_for_month(db_session, year=2026, month=5, currency="GBP")
    assert block.income_minor == 300000
    assert block.expense_minor == 180000
    assert block.net_savings_minor == 120000
    assert block.savings_rate == 40.0
    assert block.transaction_count == 2


def test_savings_rate_null_on_zero_income(db_session: Session) -> None:
    a = create_account(db_session, name="Wise GBP", currency="GBP")
    _add_tx(
        db_session,
        account_id=a.id,
        posted=date(2026, 5, 5),
        amount_minor=-1000,
        currency="GBP",
        payee="Groceries",
    )
    block = income_expense_for_month(db_session, year=2026, month=5, currency="GBP")
    assert block.income_minor == 0
    assert block.expense_minor == 1000
    assert block.net_savings_minor == -1000
    assert block.savings_rate is None


def test_drafts_excluded_from_summary(db_session: Session) -> None:
    a = create_account(db_session, name="Wise GBP", currency="GBP")
    _add_tx(
        db_session,
        account_id=a.id,
        posted=date(2026, 5, 5),
        amount_minor=100000,
        currency="GBP",
        payee="Salary",
    )
    # Insert a pending draft directly: it must not affect the summary.
    batch = IngestionBatch(
        adapter_id="wise-pdf",
        source_filename="x.pdf",
        source_size_bytes=1,
        source_sha256="0" * 64,
        account_id=a.id,
        draft_count=1,
    )
    db_session.add(batch)
    db_session.flush()
    db_session.add(
        DraftTransaction(
            batch_id=batch.id,
            account_id=a.id,
            posted_date=date(2026, 5, 6),
            amount_minor=999999,
            currency="GBP",
            payee="Big draft",
            memo=None,
            status=DraftStatus.pending,
            content_hash="x" * 64,
        )
    )
    db_session.flush()
    block = income_expense_for_month(db_session, year=2026, month=5, currency="GBP")
    assert block.income_minor == 100000
    assert block.transaction_count == 1


def test_calendar_month_boundary_inclusive(db_session: Session) -> None:
    a = create_account(db_session, name="Wise GBP", currency="GBP")
    _add_tx(
        db_session,
        account_id=a.id,
        posted=date(2026, 5, 31),
        amount_minor=-500,
        currency="GBP",
        payee="LastDay",
    )
    block = income_expense_for_month(db_session, year=2026, month=5, currency="GBP")
    assert block.transaction_count == 1
    assert block.expense_minor == 500


def test_monthly_summary_per_currency(db_session: Session) -> None:
    gbp = create_account(db_session, name="Wise GBP", currency="GBP")
    eur = create_account(db_session, name="Wise EUR", currency="EUR")
    _add_tx(
        db_session,
        account_id=gbp.id,
        posted=date(2026, 5, 1),
        amount_minor=200000,
        currency="GBP",
        payee="Salary",
    )
    _add_tx(
        db_session,
        account_id=gbp.id,
        posted=date(2026, 5, 2),
        amount_minor=-50000,
        currency="GBP",
        payee="Rent",
    )
    _add_tx(
        db_session,
        account_id=eur.id,
        posted=date(2026, 5, 5),
        amount_minor=-12345,
        currency="EUR",
        payee="Groceries",
    )

    summary = monthly_summary(db_session, year=2026, month=5)
    assert summary.year == 2026 and summary.month == 5
    assert summary.start == date(2026, 5, 1)
    assert summary.end == date(2026, 5, 31)
    by_ccy = {b.currency: b for b in summary.blocks}
    assert set(by_ccy) == {"GBP", "EUR"}
    assert by_ccy["GBP"].net_savings_minor == 150000
    assert by_ccy["GBP"].savings_rate == 75.0
    assert by_ccy["EUR"].income_minor == 0
    assert by_ccy["EUR"].expense_minor == 12345
    assert by_ccy["EUR"].savings_rate is None


def test_monthly_summary_empty_month_no_blocks(db_session: Session) -> None:
    create_account(db_session, name="Wise GBP", currency="GBP")
    summary = monthly_summary(db_session, year=2026, month=7)
    assert summary.blocks == []
    assert summary.start == date(2026, 7, 1)
    assert summary.end == date(2026, 7, 31)


def test_account_balance_snapshot(db_session: Session) -> None:
    gbp = create_account(db_session, name="Wise GBP", currency="GBP", opening_balance_minor=10000)
    eur = create_account(db_session, name="Wise EUR", currency="EUR", opening_balance_minor=0)
    _add_tx(
        db_session,
        account_id=gbp.id,
        posted=date(2026, 5, 1),
        amount_minor=15000,
        currency="GBP",
        payee="Salary",
    )
    _add_tx(
        db_session,
        account_id=eur.id,
        posted=date(2026, 5, 2),
        amount_minor=40000,
        currency="EUR",
        payee="Refund",
    )
    snapshot = account_balance_snapshot(db_session)
    by_name = {row.name: row for row in snapshot}
    assert by_name["Wise GBP"].balance_minor == 25000
    assert by_name["Wise GBP"].currency == "GBP"
    assert by_name["Wise EUR"].balance_minor == 40000
    assert by_name["Wise EUR"].currency == "EUR"
    # No total: snapshot is a list, not a single number.
    assert isinstance(snapshot, list)


def test_account_balance_snapshot_excludes_archived(db_session: Session) -> None:
    create_account(db_session, name="Live", currency="GBP")
    archived = create_account(db_session, name="Old", currency="GBP")
    archived.archived = True
    db_session.flush()
    snapshot = account_balance_snapshot(db_session)
    names = {r.name for r in snapshot}
    assert "Live" in names
    assert "Old" not in names
