"""Allow-list enforcement for Telegram updates.

The bot operates 1:1 in DMs with allow-listed users; the bot refuses to start
if the allow-list is empty (fail-closed) and silently drops messages from
non-allow-listed chats with one audit-log line per rejected chat ID.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

logger = logging.getLogger(__name__)


class EmptyAllowListError(RuntimeError):
    """Raised at startup when no chat IDs are configured."""


class AllowList:
    """Immutable set of allowed Telegram chat IDs."""

    def __init__(self, chat_ids: Iterable[int]) -> None:
        ids = {int(c) for c in chat_ids}
        if not ids:
            raise EmptyAllowListError(
                "telegram.allow_list is empty; refusing to run "
                "(fail-closed). Configure at least one chat id."
            )
        self._ids: frozenset[int] = frozenset(ids)

    def is_allowed(self, chat_id: int | None) -> bool:
        return chat_id is not None and chat_id in self._ids

    def __contains__(self, chat_id: object) -> bool:
        return isinstance(chat_id, int) and chat_id in self._ids


def audit_rejected_chat(chat_id: int | None) -> None:
    """Write one audit-log line for an update from a non-allow-listed chat."""
    logger.warning("telegram: dropping message from non-allow-listed chat %s", chat_id)
