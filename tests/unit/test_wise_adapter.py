from __future__ import annotations

from pathlib import Path

import pytest

from finance.ingestion import WiseStatementAdapter
from finance.ingestion.protocols import (
    AdapterParseError,
    InstitutionAdapter,
    ParsedTransaction,
)

FIXTURE = Path(__file__).parent.parent / "fixtures" / "wise" / "april_2026.pdf"


def test_adapter_satisfies_protocol() -> None:
    adapter = WiseStatementAdapter()
    assert isinstance(adapter, InstitutionAdapter)
    assert adapter.id == "wise-pdf"
    assert adapter.display_name == "Wise (PDF statement)"
    assert adapter.source_artifact_type == "application/pdf"


def test_parse_clean_fixture_yields_transactions() -> None:
    adapter = WiseStatementAdapter()
    parsed = list(adapter.parse(FIXTURE))
    # Sanity: > 20 lines, all in EUR, all with valid dates and non-zero amounts.
    assert len(parsed) > 20
    for tx in parsed:
        assert isinstance(tx, ParsedTransaction)
        assert tx.currency == "EUR"
        assert tx.amount_minor != 0
        assert tx.payee.strip()
        # Dates must be in the statement month (April 2026).
        assert tx.posted_date.year == 2026
        assert tx.posted_date.month == 4


def test_parse_handles_inflows_and_outflows() -> None:
    adapter = WiseStatementAdapter()
    parsed = list(adapter.parse(FIXTURE))
    inflows = [t for t in parsed if t.amount_minor > 0]
    outflows = [t for t in parsed if t.amount_minor < 0]
    assert inflows, "fixture has at least one inflow (e.g. salary, cashback)"
    assert outflows, "fixture has card transactions (outflows)"


def test_parse_signs_minor_units_correctly() -> None:
    adapter = WiseStatementAdapter()
    parsed = list(adapter.parse(FIXTURE))
    by_payee = {t.payee: t for t in parsed}
    # The first card transaction in the fixture is "Card transaction of 6.55
    # EUR issued by Netto Marken-Discount Berlin" → -655 EUR minor.
    netto = next(
        t for t in parsed
        if "Netto" in t.payee and t.amount_minor == -655 and t.posted_date.day == 30
    )
    assert netto.currency == "EUR"

    # The salary line is "Received money from SKD SE with reference LOHN..."
    salary = next(
        t for t in parsed
        if "SKD SE" in t.payee and "LOHN" in t.payee and t.amount_minor > 0
    )
    assert salary.amount_minor == 397193
    del by_payee  # only used for type-flow analysis above


def test_parse_missing_file_raises_adapter_parse_error(tmp_path: Path) -> None:
    adapter = WiseStatementAdapter()
    with pytest.raises(AdapterParseError) as exc_info:
        list(adapter.parse(tmp_path / "does-not-exist.pdf"))
    assert "wise-pdf" in str(exc_info.value)
