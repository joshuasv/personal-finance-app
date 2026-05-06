"""Secret redaction helpers used by CLI/API/log output."""

from __future__ import annotations


def redact(value: str | None, *, keep: int = 8) -> str:
    """Redact a secret to its first `keep` characters and a length suffix.

    >>> redact("sk_live_abcdef0123456789", keep=8)
    'sk_live_…(20 chars)'
    >>> redact(None)
    '<unset>'
    >>> redact("short", keep=8)
    '…(5 chars)'
    """
    if value is None or value == "":
        return "<unset>"
    n = len(value)
    if n <= keep:
        return f"…({n} chars)"
    return f"{value[:keep]}…({n} chars)"
