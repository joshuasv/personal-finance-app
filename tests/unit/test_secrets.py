from __future__ import annotations

from finance.core.secrets import redact


def test_redact_unset_value() -> None:
    assert redact(None) == "<unset>"
    assert redact("") == "<unset>"


def test_redact_short_value_hides_content_but_shows_length() -> None:
    out = redact("abc", keep=8)
    assert "abc" not in out
    assert "(3 chars)" in out


def test_redact_long_value_keeps_prefix_and_shows_length() -> None:
    out = redact("sk_live_abcdef0123456789", keep=8)
    assert out.startswith("sk_live_")
    assert "(24 chars)" in out
    assert "abcdef" not in out
