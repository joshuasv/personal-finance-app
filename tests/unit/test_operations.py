from __future__ import annotations

import pytest
from pydantic import ValidationError as PydValidationError
from sqlalchemy.orm import Session

from finance.core.operations import build_default_registry
from finance.core.operations.bootstrap import _OPERATIONS


def test_registry_contains_all_expected_operations() -> None:
    expected = {
        "create_account",
        "archive_account",
        "list_accounts",
        "record_transaction",
        "update_transaction",
        "delete_transaction",
        "list_transactions",
        "account_balance",
        "list_adapters",
        "import_artifact",
        "list_drafts",
        "confirm_draft",
        "reject_draft",
        "monthly_summary",
        "income_expense_for_month",
        "account_balance_snapshot",
    }
    registry = build_default_registry()
    assert set(registry.names()) == expected


def test_registry_lookup_and_iteration() -> None:
    registry = build_default_registry()
    op = registry.get("create_account")
    assert op.name == "create_account"
    assert op.input_model.__name__ == "CreateAccountIn"
    assert {o.name for o in registry} == set(registry.names())
    assert len(registry) == len(_OPERATIONS)


def test_registry_double_register_rejected() -> None:
    registry = build_default_registry()
    with pytest.raises(ValueError, match="already registered"):
        registry.register(registry.get("create_account"))


def test_registry_get_unknown_raises() -> None:
    registry = build_default_registry()
    with pytest.raises(KeyError):
        registry.get("nope")


def test_create_account_input_rejects_float_amount() -> None:
    op = build_default_registry().get("create_account")
    with pytest.raises(PydValidationError) as exc_info:
        op.input_model(
            name="X",
            currency="GBP",
            opening_balance_minor=12.50,
        )
    msg = str(exc_info.value)
    assert "minor units" in msg


def test_create_account_input_rejects_bad_currency() -> None:
    op = build_default_registry().get("create_account")
    with pytest.raises(PydValidationError):
        op.input_model(name="X", currency="GB")


def test_create_account_input_rejects_extra_field() -> None:
    op = build_default_registry().get("create_account")
    with pytest.raises(PydValidationError):
        op.input_model(name="X", currency="GBP", type="checking")  # type: ignore[call-arg]


def test_record_transaction_input_rejects_float_amount() -> None:
    op = build_default_registry().get("record_transaction")
    with pytest.raises(PydValidationError):
        op.input_model(
            account_id=1,
            posted_date="2026-05-01",
            amount_minor=12.50,
            currency="GBP",
            payee="X",
        )


def test_create_account_callable_round_trips(db_session: Session) -> None:
    op = build_default_registry().get("create_account")
    payload = op.input_model(
        name="Wise GBP",
        currency="GBP",
        opening_balance_minor=0,
    )
    out = op.callable(db_session, payload)
    assert isinstance(out, op.output_model)
    assert out.account.name == "Wise GBP"
    assert out.account.currency == "GBP"


def test_account_balance_callable(db_session: Session) -> None:
    registry = build_default_registry()
    create = registry.get("create_account")
    record = registry.get("record_transaction")
    balance = registry.get("account_balance")

    created = create.callable(
        db_session,
        create.input_model(
            name="Wise GBP",
            currency="GBP",
            opening_balance_minor=10000,
        ),
    )
    aid = created.account.id

    record.callable(
        db_session,
        record.input_model(
            account_id=aid,
            posted_date="2026-05-01",
            amount_minor=-2500,
            currency="GBP",
            payee="Tesco",
        ),
    )

    out = balance.callable(db_session, balance.input_model(account_id=aid))
    assert out.balance_minor == 7500
    assert out.currency == "GBP"
