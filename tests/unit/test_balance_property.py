from __future__ import annotations

import uuid
from datetime import date, timedelta

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy.orm import Session, sessionmaker

from finance.core.services import (
    account_balance,
    create_account,
    record_transaction,
)


@given(
    opening=st.integers(min_value=-(10**9), max_value=10**9),
    amounts=st.lists(
        st.integers(min_value=-(10**8), max_value=10**8).filter(lambda x: x != 0),
        min_size=0,
        max_size=30,
        unique=True,
    ),
)
@settings(
    max_examples=40,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_balance_equals_opening_plus_sum(
    session_factory: sessionmaker[Session], opening: int, amounts: list[int]
) -> None:
    name = f"acct-{uuid.uuid4().hex}"
    with session_factory() as session:
        account = create_account(
            session,
            name=name,
            currency="GBP",
            opening_balance_minor=opening,
        )
        for offset, amt in enumerate(amounts):
            record_transaction(
                session,
                account_id=account.id,
                posted_date=date(2026, 1, 1) + timedelta(days=offset),
                amount_minor=amt,
                currency="GBP",
                payee=f"p-{offset}",
            )
        session.commit()

        bal = account_balance(session, account_id=account.id)
        assert bal.minor == opening + sum(amounts)
        assert bal.currency == "GBP"
