from __future__ import annotations

import pytest

from finance.core.money import Money, decimals_for, is_valid_iso_currency


def test_decimals_for_common_currencies() -> None:
    assert decimals_for("GBP") == 2
    assert decimals_for("USD") == 2
    assert decimals_for("EUR") == 2
    assert decimals_for("JPY") == 0
    assert decimals_for("BHD") == 3


def test_is_valid_iso_currency_shape() -> None:
    assert is_valid_iso_currency("GBP")
    assert not is_valid_iso_currency("gbp")
    assert not is_valid_iso_currency("GB")
    assert not is_valid_iso_currency("GBPP")


def test_money_format_two_decimal() -> None:
    assert Money(1250, "GBP").format() == "12.50 GBP"
    assert Money(-300, "USD").format() == "-3.00 USD"
    assert Money(0, "EUR").format() == "0.00 EUR"


def test_money_format_zero_decimal() -> None:
    assert Money(1000, "JPY").format() == "1000 JPY"
    assert Money(-3, "JPY").format() == "-3 JPY"


def test_money_format_three_decimal() -> None:
    assert Money(1234, "BHD").format() == "1.234 BHD"


def test_money_rejects_float_minor() -> None:
    with pytest.raises(TypeError):
        Money(12.5, "GBP")  # type: ignore[arg-type]


def test_money_rejects_bad_currency() -> None:
    with pytest.raises(ValueError):
        Money(100, "gbp")


def test_money_parse_round_trip() -> None:
    cases = [
        ("12.50 GBP", Money(1250, "GBP")),
        ("-3.00 USD", Money(-300, "USD")),
        ("0.00 EUR", Money(0, "EUR")),
        ("1000 JPY", Money(1000, "JPY")),
        ("-3 JPY", Money(-3, "JPY")),
        ("1.234 BHD", Money(1234, "BHD")),
        ("12 GBP", Money(1200, "GBP")),
    ]
    for text, expected in cases:
        parsed = Money.parse(text)
        assert parsed == expected
        assert parsed.format() == expected.format()


def test_money_parse_rejects_too_many_decimals() -> None:
    with pytest.raises(ValueError):
        Money.parse("12.501 GBP")


def test_money_parse_rejects_decimal_for_zero_decimal_currency() -> None:
    with pytest.raises(ValueError):
        Money.parse("12.50 JPY")
