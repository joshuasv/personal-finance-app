"""Level-2 dispatcher tests for the Telegram bot.

These tests build the *real* `python-telegram-bot` `Application` via
`build_application(...)`, swap its `bot` attribute for a `_StubBot` that
records outgoing calls, and dispatch synthetic `Update` objects through
`Application.process_update(...)`.

This is the layer where the user-visible "bot is silent" failure lives:
the existing Level-1 tests in `test_telegram_bot.py` call handler functions
directly, bypassing handler registration, filter matching, and dispatcher
routing — so a regression in any of those is invisible to CI.

GIVEN / WHEN / THEN structure mirrors the OpenSpec scenarios in
`telegram-bot/spec.md`.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from telegram import Chat, Document, Message, Update, User
from telegram._telegramobject import TelegramObject
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler

from finance.bots.telegram.app import build_application
from finance.core.config import DatabaseSettings, Settings, TelegramSettings
from finance.core.operations import build_default_registry
from finance.core.services import create_account

pytestmark = pytest.mark.integration

ALLOWED_CHAT = 12345
DENIED_CHAT = 99999
TOKEN = "0000000000:fake-test-token-not-real"


# --- Stub bot ----------------------------------------------------------------


class _StubFile:
    """Stand-in for `telegram.File` returned by `bot.get_file`."""

    def __init__(self, data: bytes) -> None:
        self._data = data

    async def download_as_bytearray(self) -> bytearray:
        return bytearray(self._data)


class _StubBot:
    """Records outgoing bot calls instead of hitting api.telegram.org.

    Only methods our handlers actually invoke are implemented. Any other
    call will raise `AttributeError`, which is intentional — a silent
    `MagicMock`-style auto-attr would mask handler bugs.
    """

    def __init__(self, *, file_data: bytes = b"") -> None:
        self.id = 1
        self.username = "stub_bot"
        self.first_name = "stub"
        self.token = TOKEN
        self.sent_messages: list[dict[str, Any]] = []
        self.edited_messages: list[dict[str, Any]] = []
        self.callback_answers: list[str] = []
        self._file_data = file_data
        self._initialized = False

    # PTB Application lifecycle ------------------------------------------------

    async def initialize(self) -> None:
        self._initialized = True

    async def shutdown(self) -> None:
        self._initialized = False

    async def get_me(self, **_kwargs: Any) -> User:
        return User(id=self.id, is_bot=True, first_name=self.first_name, username=self.username)

    # Outgoing surfaces our handlers use --------------------------------------

    async def send_message(self, chat_id: int, text: str, **kwargs: Any) -> Message:
        self.sent_messages.append({"chat_id": chat_id, "text": text, **kwargs})
        return Message(
            message_id=len(self.sent_messages) + 1000,
            date=datetime.now(UTC),
            chat=Chat(id=chat_id, type=Chat.PRIVATE),
            text=text,
        )

    async def edit_message_text(
        self,
        text: str,
        chat_id: int | None = None,
        message_id: int | None = None,
        inline_message_id: str | None = None,
        **kwargs: Any,
    ) -> Message | bool:
        self.edited_messages.append(
            {
                "text": text,
                "chat_id": chat_id,
                "message_id": message_id,
                **kwargs,
            }
        )
        return Message(
            message_id=message_id or 1,
            date=datetime.now(UTC),
            chat=Chat(id=chat_id or 0, type=Chat.PRIVATE),
            text=text,
        )

    async def answer_callback_query(self, callback_query_id: str, **_kwargs: Any) -> bool:
        self.callback_answers.append(callback_query_id)
        return True

    async def get_file(self, file_id: str, **_kwargs: Any) -> _StubFile:
        return _StubFile(self._file_data)


# --- Update builders ---------------------------------------------------------


def _attach_bot(obj: Any, bot: Any) -> None:
    """Recursively associate `bot` with every TelegramObject reachable from `obj`.

    PTB's `set_bot` is not recursive in v22; CommandHandler.check_update calls
    `message.get_bot()` and trips a RuntimeError otherwise. PTB objects use
    `__slots__`, so we walk slot names from the MRO.
    """
    if isinstance(obj, TelegramObject):
        obj.set_bot(bot)
        slot_names: set[str] = set()
        for klass in type(obj).__mro__:
            slot_names.update(getattr(klass, "__slots__", ()) or ())
        for name in slot_names:
            child = getattr(obj, name, None)
            _attach_bot(child, bot)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            _attach_bot(item, bot)


def _build_text_update(chat_id: int, text: str, *, update_id: int = 1) -> Update:
    """Build a real `Update` representing a text message in a private chat."""
    chat = Chat(id=chat_id, type=Chat.PRIVATE)
    user = User(id=chat_id, is_bot=False, first_name="tester", username="tester")
    msg = Message(
        message_id=update_id * 10,
        date=datetime.now(UTC),
        chat=chat,
        from_user=user,
        text=text,
    )
    if text.startswith("/"):
        # Slash commands need a bot_command entity for CommandHandler to match.
        from telegram import MessageEntity

        msg = Message(
            message_id=update_id * 10,
            date=datetime.now(UTC),
            chat=chat,
            from_user=user,
            text=text,
            entities=[MessageEntity(type=MessageEntity.BOT_COMMAND, offset=0, length=len(text))],
        )
    return Update(update_id=update_id, message=msg)


def _build_document_update(
    chat_id: int,
    *,
    file_id: str,
    file_name: str,
    mime_type: str,
    update_id: int = 1,
) -> Update:
    """Build a real `Update` representing a document upload."""
    chat = Chat(id=chat_id, type=Chat.PRIVATE)
    user = User(id=chat_id, is_bot=False, first_name="tester", username="tester")
    document = Document(
        file_id=file_id,
        file_unique_id=f"{file_id}-uniq",
        file_name=file_name,
        mime_type=mime_type,
        file_size=128,
    )
    msg = Message(
        message_id=update_id * 10,
        date=datetime.now(UTC),
        chat=chat,
        from_user=user,
        document=document,
    )
    return Update(update_id=update_id, message=msg)


# --- Fixtures ----------------------------------------------------------------


@pytest.fixture
def bot_settings(db_path: Path) -> Settings:
    return Settings(
        db=DatabaseSettings(path=db_path),
        telegram=TelegramSettings(token=TOKEN, allow_list=[ALLOWED_CHAT]),
    )


@pytest.fixture
def bot_session_maker(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


@pytest.fixture
async def app_and_bot(
    bot_settings: Settings,
    bot_session_maker: sessionmaker,
) -> AsyncIterator[tuple[Application, _StubBot]]:
    """Build a real Application, swap in a stub bot, initialize, yield, shut down."""
    application = build_application(
        bot_settings,
        registry=build_default_registry(),
        session_maker=bot_session_maker,
    )
    stub = _StubBot()
    # Replace the bot before initialize() so PTB's lifecycle uses the stub.
    application.bot = stub  # type: ignore[assignment]
    # Drop the updater: it holds its own reference to the real bot and would
    # try to call api.telegram.org during initialize(). We never use polling
    # in these tests — we drive Application.process_update(...) directly.
    application.updater = None  # type: ignore[assignment]
    await application.initialize()
    try:
        yield application, stub
    finally:
        await application.shutdown()


# --- 1.5 Sanity check: handlers are registered ------------------------------


def test_application_registers_documented_handlers(
    bot_settings: Settings, bot_session_maker: sessionmaker
) -> None:
    """If a handler is missing here, every dispatcher test below would fail
    silently — this catches the 'handler never registered' failure mode
    without dispatching anything."""
    application = build_application(
        bot_settings,
        registry=build_default_registry(),
        session_maker=bot_session_maker,
    )
    flat = [hh for group in application.handlers.values() for hh in group]
    command_names: set[str] = set()
    for hh in flat:
        if isinstance(hh, CommandHandler) and hh.commands:
            command_names.update(hh.commands)
    assert {"help", "start", "balance", "summary", "drafts"} <= command_names
    assert any(isinstance(hh, MessageHandler) for hh in flat), "document MessageHandler missing"
    assert any(isinstance(hh, CallbackQueryHandler) for hh in flat), "callback handler missing"


# --- 2.1 /help is reachable through the dispatcher --------------------------


async def test_when_allowed_chat_sends_help_then_bot_replies_via_dispatcher(
    app_and_bot: tuple[Application, _StubBot],
) -> None:
    application, stub = app_and_bot
    update = _build_text_update(ALLOWED_CHAT, "/help")
    _attach_bot(update, application.bot)

    await application.process_update(update)

    assert len(stub.sent_messages) == 1, (
        f"expected one send_message, got {len(stub.sent_messages)}: {stub.sent_messages}"
    )
    assert "Commands" in stub.sent_messages[0]["text"]


# --- 2.2 PDF upload reaches the dispatcher and prompts -----------------------


async def test_when_allowed_chat_sends_pdf_then_bot_replies_with_picker(
    app_and_bot: tuple[Application, _StubBot],
    db_session: Any,
) -> None:
    application, stub = app_and_bot
    create_account(db_session, name="Wise EUR", currency="EUR")
    db_session.commit()
    stub._file_data = b"%PDF-1.4\n" + b"A" * 256

    update = _build_document_update(
        ALLOWED_CHAT,
        file_id="fake-file-id",
        file_name="april_2026.pdf",
        mime_type="application/pdf",
    )
    _attach_bot(update, application.bot)

    await application.process_update(update)

    assert len(stub.sent_messages) >= 1, (
        f"expected at least one send_message, got {len(stub.sent_messages)}"
    )
    last = stub.sent_messages[-1]
    assert "PDF saved" in last["text"]
    assert last.get("reply_markup") is not None, "expected an inline keyboard reply_markup"


# --- 2.3 PDF with octet-stream mime is still handled -------------------------


async def test_when_allowed_chat_sends_pdf_with_octet_stream_mime_then_bot_still_handles_it(
    app_and_bot: tuple[Application, _StubBot],
    db_session: Any,
) -> None:
    """Telegram occasionally emits `application/octet-stream` for PDF uploads.
    The bot must accept those when the file_name ends in `.pdf`."""
    application, stub = app_and_bot
    create_account(db_session, name="Wise EUR", currency="EUR")
    db_session.commit()
    stub._file_data = b"%PDF-1.4\n" + b"B" * 256

    update = _build_document_update(
        ALLOWED_CHAT,
        file_id="fake-file-id-2",
        file_name="april_2026.pdf",
        mime_type="application/octet-stream",
    )
    _attach_bot(update, application.bot)

    await application.process_update(update)

    assert len(stub.sent_messages) >= 1
    last = stub.sent_messages[-1]
    assert "PDF saved" in last["text"], (
        f"expected 'PDF saved' reply for octet-stream PDF, got: {last['text']!r}"
    )
    assert last.get("reply_markup") is not None


# --- 2.4 Disallowed chat is silently dropped and audited ---------------------


async def test_when_disallowed_chat_sends_help_then_bot_does_not_reply_and_logs_audit_line(
    app_and_bot: tuple[Application, _StubBot],
    caplog: pytest.LogCaptureFixture,
) -> None:
    application, stub = app_and_bot
    update = _build_text_update(DENIED_CHAT, "/help")
    _attach_bot(update, application.bot)

    with caplog.at_level(logging.WARNING):
        await application.process_update(update)

    assert stub.sent_messages == [], (
        f"disallowed chat must not receive a reply, got: {stub.sent_messages}"
    )
    audit_lines = [r for r in caplog.records if str(DENIED_CHAT) in r.getMessage()]
    assert len(audit_lines) == 1, (
        f"expected exactly one audit log line for chat {DENIED_CHAT}; "
        f"got {len(audit_lines)}: {[r.getMessage() for r in audit_lines]}"
    )
