"""Build a `python-telegram-bot` Application wired to `core.operations`.

`build_application(settings)` returns a fully-configured Application; the
caller invokes `application.run_polling()` (typically from the CLI's `bot`
command). The factory also instantiates the inbox directory at mode 0700 so
the very first PDF upload doesn't race-create it.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import sessionmaker
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from finance.bots.telegram.auth import AllowList
from finance.bots.telegram.handlers import (
    CTX_KEY,
    BotDeps,
    balance_command,
    callback_handler,
    document_handler,
    drafts_command,
    help_command,
    start_command,
    summary_command,
)
from finance.bots.telegram.inbox import inbox_dir
from finance.core.config import Settings
from finance.core.db import engine_for, session_factory_for
from finance.core.logging import configure_logging
from finance.core.operations import OperationRegistry, build_default_registry

logger = logging.getLogger(__name__)


def build_application(
    settings: Settings,
    *,
    registry: OperationRegistry | None = None,
    session_maker: sessionmaker | None = None,
) -> Application:
    """Assemble the Application with all handlers registered.

    Raises `EmptyAllowListError` if `telegram.allow_list` is empty.
    """
    if settings.telegram.token is None or settings.telegram.token == "":
        raise RuntimeError(
            "telegram.token is not set; cannot build the bot Application"
        )

    # Ensure logging redaction is in place before any handler runs.
    configure_logging(settings)
    allow_list = AllowList(settings.telegram.allow_list)

    # Pre-create the inbox so the first upload doesn't race the mkdir.
    inbox_dir()

    if registry is None:
        registry = build_default_registry()
    if session_maker is None:
        engine = engine_for(settings.db.path)
        session_maker = session_factory_for(engine)

    application = ApplicationBuilder().token(settings.telegram.token).build()
    application.bot_data[CTX_KEY] = BotDeps(
        settings=settings,
        registry=registry,
        session_maker=session_maker,
        allow_list=allow_list,
    )

    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("balance", balance_command))
    application.add_handler(CommandHandler("summary", summary_command))
    application.add_handler(CommandHandler("drafts", drafts_command))
    application.add_handler(MessageHandler(filters.Document.ALL, document_handler))
    application.add_handler(CallbackQueryHandler(callback_handler))

    logger.info("bot ready (allow-listed chats: %d)", len(settings.telegram.allow_list))
    return application


__all__ = ["build_application"]
