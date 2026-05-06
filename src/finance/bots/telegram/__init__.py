"""Telegram bot: deterministic dispatcher over `core.operations`.

v1 holds no LLM in the loop — every action is either a slash command that
maps 1:1 to a registered operation, or a PDF upload that flows through the
`import_artifact` operation.
"""

from finance.bots.telegram.app import build_application

__all__ = ["build_application"]
