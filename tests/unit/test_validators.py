from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from finance.core.validators import CurrencyCode, MinorUnits


class _Demo(BaseModel):
    amount: MinorUnits
    currency: CurrencyCode


def test_minor_units_accepts_int() -> None:
    obj = _Demo(amount=1250, currency="GBP")
    assert obj.amount == 1250


def test_minor_units_rejects_float() -> None:
    with pytest.raises(ValidationError) as exc:
        _Demo(amount=12.5, currency="GBP")  # type: ignore[arg-type]
    msg = str(exc.value)
    assert "minor units" in msg


def test_minor_units_rejects_bool() -> None:
    with pytest.raises(ValidationError):
        _Demo(amount=True, currency="GBP")  # type: ignore[arg-type]


def test_currency_code_uppercases_and_validates() -> None:
    obj = _Demo(amount=100, currency="gbp")
    assert obj.currency == "GBP"


def test_currency_code_rejects_bad_shape() -> None:
    with pytest.raises(ValidationError):
        _Demo(amount=100, currency="GB")
    with pytest.raises(ValidationError):
        _Demo(amount=100, currency="GBPP")


def test_validation_via_json_rejects_decimal_amount() -> None:
    """Mirrors the API surface: a JSON request with a decimal amount must fail."""
    with pytest.raises(ValidationError):
        _Demo.model_validate_json('{"amount": 12.50, "currency": "GBP"}')


def test_validation_via_json_accepts_integer_amount() -> None:
    obj = _Demo.model_validate_json('{"amount": 1250, "currency": "GBP"}')
    assert obj.amount == 1250
    assert obj.currency == "GBP"
