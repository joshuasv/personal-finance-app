from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.orm import Session

from finance.core.services import (
    AccountArchivedError,
    AccountNotFoundError,
    AmountZeroError,
    CurrencyMismatchError,
    DuplicateTransactionError,
    TransactionNotFoundError,
    ValidationError,
    account_balance,
    archive_account,
    create_account,
    delete_transaction,
    list_transactions,
    record_transaction,
    update_transaction,
)


def _wise_gbp(session: Session, opening: int = 0) -> int:
    a = create_account(
        session,
        name="Wise GBP",
        currency="GBP",
        opening_balance_minor=opening,
    )
    return a.id


def test_record_manual_outflow(db_session: Session) -> None:
    aid = _wise_gbp(db_session)
    tx = record_transaction(
        db_session,
        account_id=aid,
        posted_date=date(2026, 5, 1),
        amount_minor=-1250,
        currency="GBP",
        payee="Tesco",
    )
    assert tx.entered_by == "manual"
    assert tx.currency == "GBP"
    assert tx.content_hash and len(tx.content_hash) == 64


def test_record_imported_tag(db_session: Session) -> None:
    aid = _wise_gbp(db_session)
    tx = record_transaction(
        db_session,
        account_id=aid,
        posted_date=date(2026, 5, 1),
        amount_minor=-1250,
        currency="GBP",
        payee="Tesco",
        entered_by="imported:wise-pdf",
    )
    assert tx.entered_by == "imported:wise-pdf"


def test_currency_mismatch_rejected(db_session: Session) -> None:
    aid = _wise_gbp(db_session)
    with pytest.raises(CurrencyMismatchError):
        record_transaction(
            db_session,
            account_id=aid,
            posted_date=date(2026, 5, 1),
            amount_minor=-100,
            currency="EUR",
            payee="X",
        )


def test_zero_amount_rejected(db_session: Session) -> None:
    aid = _wise_gbp(db_session)
    with pytest.raises(AmountZeroError):
        record_transaction(
            db_session,
            account_id=aid,
            posted_date=date(2026, 5, 1),
            amount_minor=0,
            currency="GBP",
            payee="X",
        )


def test_blank_payee_rejected(db_session: Session) -> None:
    aid = _wise_gbp(db_session)
    with pytest.raises(ValidationError):
        record_transaction(
            db_session,
            account_id=aid,
            posted_date=date(2026, 5, 1),
            amount_minor=-100,
            currency="GBP",
            payee="   ",
        )


def test_unknown_account_rejected(db_session: Session) -> None:
    with pytest.raises(AccountNotFoundError):
        record_transaction(
            db_session,
            account_id=999_999,
            posted_date=date(2026, 5, 1),
            amount_minor=-100,
            currency="GBP",
            payee="X",
        )


def test_archived_account_rejected(db_session: Session) -> None:
    aid = _wise_gbp(db_session)
    archive_account(db_session, account_id=aid)
    with pytest.raises(AccountArchivedError):
        record_transaction(
            db_session,
            account_id=aid,
            posted_date=date(2026, 5, 1),
            amount_minor=-100,
            currency="GBP",
            payee="X",
        )


def test_duplicate_content_hash_rejected(db_session: Session) -> None:
    aid = _wise_gbp(db_session)
    record_transaction(
        db_session,
        account_id=aid,
        posted_date=date(2026, 5, 1),
        amount_minor=-1250,
        currency="GBP",
        payee="Tesco",
    )
    with pytest.raises(DuplicateTransactionError):
        record_transaction(
            db_session,
            account_id=aid,
            posted_date=date(2026, 5, 1),
            amount_minor=-1250,
            currency="GBP",
            payee="Tesco",
        )


def test_balance_empty_returns_opening(db_session: Session) -> None:
    aid = _wise_gbp(db_session, opening=10000)
    bal = account_balance(db_session, account_id=aid)
    assert bal.minor == 10000
    assert bal.currency == "GBP"


def test_balance_sums_inflows_and_outflows(db_session: Session) -> None:
    aid = _wise_gbp(db_session, opening=10000)
    for amount, payee in [(5000, "salary"), (-1500, "Tesco"), (-200, "bus")]:
        record_transaction(
            db_session,
            account_id=aid,
            posted_date=date(2026, 5, 1),
            amount_minor=amount,
            currency="GBP",
            payee=payee,
        )
    bal = account_balance(db_session, account_id=aid)
    assert bal.minor == 13300


def test_update_transaction_changes_fields(db_session: Session) -> None:
    aid = _wise_gbp(db_session)
    tx = record_transaction(
        db_session,
        account_id=aid,
        posted_date=date(2026, 5, 1),
        amount_minor=-1000,
        currency="GBP",
        payee="Tesco",
    )
    old_hash = tx.content_hash
    updated = update_transaction(
        db_session, transaction_id=tx.id, amount_minor=-2000, payee="Tesco Metro"
    )
    assert updated.amount_minor == -2000
    assert updated.payee == "Tesco Metro"
    assert updated.content_hash != old_hash


def test_update_transaction_zero_amount_rejected(db_session: Session) -> None:
    aid = _wise_gbp(db_session)
    tx = record_transaction(
        db_session,
        account_id=aid,
        posted_date=date(2026, 5, 1),
        amount_minor=-1000,
        currency="GBP",
        payee="Tesco",
    )
    with pytest.raises(AmountZeroError):
        update_transaction(db_session, transaction_id=tx.id, amount_minor=0)


def test_update_transaction_collision_rejected(db_session: Session) -> None:
    aid = _wise_gbp(db_session)
    record_transaction(
        db_session,
        account_id=aid,
        posted_date=date(2026, 5, 1),
        amount_minor=-1000,
        currency="GBP",
        payee="A",
    )
    other = record_transaction(
        db_session,
        account_id=aid,
        posted_date=date(2026, 5, 1),
        amount_minor=-2000,
        currency="GBP",
        payee="B",
    )
    with pytest.raises(DuplicateTransactionError):
        update_transaction(
            db_session, transaction_id=other.id, amount_minor=-1000, payee="A"
        )


def test_delete_transaction(db_session: Session) -> None:
    aid = _wise_gbp(db_session)
    tx = record_transaction(
        db_session,
        account_id=aid,
        posted_date=date(2026, 5, 1),
        amount_minor=-1000,
        currency="GBP",
        payee="Tesco",
    )
    delete_transaction(db_session, transaction_id=tx.id)
    with pytest.raises(TransactionNotFoundError):
        delete_transaction(db_session, transaction_id=tx.id)


def test_list_transactions_filters_by_date_range(db_session: Session) -> None:
    aid = _wise_gbp(db_session)
    for d, amt, payee in [
        (date(2026, 4, 30), -500, "April"),
        (date(2026, 5, 1), -100, "May1"),
        (date(2026, 5, 15), -200, "May15"),
        (date(2026, 6, 1), -300, "June"),
    ]:
        record_transaction(
            db_session,
            account_id=aid,
            posted_date=d,
            amount_minor=amt,
            currency="GBP",
            payee=payee,
        )
    rows = list_transactions(
        db_session,
        account_id=aid,
        start=date(2026, 5, 1),
        end=date(2026, 5, 31),
    )
    assert [r.payee for r in rows] == ["May1", "May15"]
