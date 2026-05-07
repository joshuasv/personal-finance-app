"""Logging setup for the app.

The single rule: secrets never appear in log output. We attach a filter that
scrubs known secret values from every log record before it's emitted.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from typing import Any

from finance.core.config import Settings
from finance.core.secrets import redact

_REDACTED = "***"


class SecretRedactingFilter(logging.Filter):
    """Filter that scrubs a list of secret values out of every log record."""

    def __init__(self, secrets: Iterable[str]) -> None:
        super().__init__()
        self._patterns: list[re.Pattern[str]] = [re.compile(re.escape(s)) for s in secrets if s]

    def add_secret(self, secret: str) -> None:
        if not secret:
            return
        self._patterns.append(re.compile(re.escape(secret)))

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self._scrub(str(record.getMessage()))
        # We've already formatted args into the message; clear them so the
        # logger doesn't reformat with the original (un-scrubbed) values.
        record.args = ()
        return True

    def _scrub(self, text: str) -> str:
        for p in self._patterns:
            text = p.sub(_REDACTED, text)
        return text


def configure_logging(settings: Settings) -> SecretRedactingFilter:
    """Configure the root logger and attach a redaction filter.

    Returns the filter so callers (e.g., the Telegram bot) can register
    additional secrets at runtime.
    """
    secrets: list[str] = []
    if settings.api.key:
        secrets.append(settings.api.key)
    if settings.telegram.token:
        secrets.append(settings.telegram.token)

    redactor = SecretRedactingFilter(secrets)

    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    handler.addFilter(redactor)

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(getattr(logging, settings.log.level.upper(), logging.INFO))
    root.addFilter(redactor)
    return redactor


def safe_describe_settings(settings: Settings) -> dict[str, Any]:
    """A dict suitable for logging: secrets redacted, paths stringified."""
    return {
        "db_path": str(settings.db.path),
        "api_host": settings.api.host,
        "api_port": settings.api.port,
        "api_key": redact(settings.api.key) if settings.api.key else None,
        "telegram_token": (redact(settings.telegram.token) if settings.telegram.token else None),
        "telegram_allow_list_count": len(settings.telegram.allow_list),
        "log_level": settings.log.level,
    }
