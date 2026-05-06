from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from finance.core.services import (
    AccountInUseError,
    AccountNotFoundError,
    DuplicateAccountNameError,
    ValidationError,
    archive_account,
    create_account,
    list_accounts,
    record_transaction,
)


def test_create_account_persists_fields(db_session: Session) -> None:
    a = create_account(
        db_session,
        name="Wise GBP",
        currency="GBP",
        opening_balance_minor=0,
    )
    assert a.id is not None
    assert a.name == "Wise GBP"
    assert a.currency == "GBP"
    assert a.archived is False


def test_create_account_uppercases_currency(db_session: Session) -> None:
    a = create_account(db_session, name="Wise USD", currency="usd")
    assert a.currency == "USD"


def test_create_account_rejects_duplicate_active_name(db_session: Session) -> None:
    create_account(db_session, name="Wise GBP", currency="GBP")
    with pytest.raises(DuplicateAccountNameError):
        create_account(db_session, name="Wise GBP", currency="GBP")


def test_create_account_rejects_non_iso_currency(db_session: Session) -> None:
    with pytest.raises(ValidationError):
        create_account(db_session, name="A", currency="GB")


def test_create_account_rejects_blank_name(db_session: Session) -> None:
    with pytest.raises(ValidationError):
        create_account(db_session, name="   ", currency="GBP")


def test_archive_then_create_same_name_succeeds(db_session: Session) -> None:
    a = create_account(db_session, name="Wise GBP", currency="GBP")
    archive_account(db_session, account_id=a.id)
    b = create_account(db_session, name="Wise GBP", currency="GBP")
    assert b.id != a.id and b.archived is False


def test_archive_unknown_account(db_session: Session) -> None:
    with pytest.raises(AccountNotFoundError):
        archive_account(db_session, account_id=999_999)


def test_archive_refuses_with_transactions(db_session: Session) -> None:
    from datetime import date

    a = create_account(db_session, name="Wise GBP", currency="GBP")
    record_transaction(
        db_session,
        account_id=a.id,
        posted_date=date(2026, 5, 1),
        amount_minor=-1250,
        currency="GBP",
        payee="Tesco",
    )
    with pytest.raises(AccountInUseError):
        archive_account(db_session, account_id=a.id)


def test_list_accounts_excludes_archived_by_default(db_session: Session) -> None:
    a = create_account(db_session, name="A", currency="GBP")
    create_account(db_session, name="B", currency="GBP")
    archive_account(db_session, account_id=a.id)
    assert {x.name for x in list_accounts(db_session)} == {"B"}
    assert {x.name for x in list_accounts(db_session, include_archived=True)} == {
        "A",
        "B",
    }
