"""Integration tests for the Telegram bot.

These tests drive the handler functions directly with mock Update/Context
objects — they don't talk to Telegram. The PDF document handler exercises
the inbox-saving + adapter/account picker + import_artifact flow end-to-end.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from finance.bots.telegram import handlers as h
from finance.bots.telegram.app import build_application
from finance.bots.telegram.auth import AllowList, EmptyAllowListError
from finance.bots.telegram.inbox import save_pdf_bytes
from finance.core.config import (
    DatabaseSettings,
    Settings,
    TelegramSettings,
)
from finance.core.logging import configure_logging
from finance.core.operations import build_default_registry

pytestmark = pytest.mark.integration

ALLOWED_CHAT = 12345
DENIED_CHAT = 99999
TOKEN = "0000000000:fake-test-token-not-real"


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
def deps(
    bot_settings: Settings, bot_session_maker: sessionmaker
) -> h.BotDeps:
    return h.BotDeps(
        settings=bot_settings,
        registry=build_default_registry(),
        session_maker=bot_session_maker,
        allow_list=AllowList([ALLOWED_CHAT]),
    )


def _make_update(chat_id: int = ALLOWED_CHAT, *, message: bool = True) -> MagicMock:
    update = MagicMock(name="Update")
    update.effective_chat = MagicMock(id=chat_id)
    update.effective_user = MagicMock(id=chat_id, is_bot=False, username="tester")
    if message:
        msg = MagicMock(name="Message")
        msg.reply_text = AsyncMock()
        update.message = msg
    else:
        update.message = None
    return update


def _make_context(deps: h.BotDeps, args: list[str] | None = None) -> MagicMock:
    context = MagicMock(name="Context")
    context.bot_data = {h.CTX_KEY: deps}
    context.user_data = {}
    context.args = args or []
    bot_mock = MagicMock(name="Bot")
    bot_mock.get_file = AsyncMock()
    context.bot = bot_mock
    return context


# --- Allow-list checks -------------------------------------------------------


async def test_help_drops_non_allow_listed_chat(
    deps: h.BotDeps, caplog: pytest.LogCaptureFixture
) -> None:
    update = _make_update(chat_id=DENIED_CHAT)
    context = _make_context(deps)
    with caplog.at_level(logging.WARNING):
        await h.help_command(update, context)
    update.message.reply_text.assert_not_called()
    assert any(str(DENIED_CHAT) in r.getMessage() for r in caplog.records)


async def test_help_replies_for_allow_listed_chat(deps: h.BotDeps) -> None:
    update = _make_update(chat_id=ALLOWED_CHAT)
    context = _make_context(deps)
    await h.help_command(update, context)
    update.message.reply_text.assert_awaited_once()
    args, _ = update.message.reply_text.call_args
    assert "Commands" in args[0]


async def test_start_aliases_help(deps: h.BotDeps) -> None:
    update = _make_update()
    context = _make_context(deps)
    await h.start_command(update, context)
    update.message.reply_text.assert_awaited_once()
    args, _ = update.message.reply_text.call_args
    assert "Commands" in args[0]


# --- Slash command behavior --------------------------------------------------


async def test_balance_lists_per_account(
    deps: h.BotDeps, db_session
) -> None:
    from finance.core.services import create_account, record_transaction
    from datetime import date

    a = create_account(
        db_session, name="Wise GBP", currency="GBP", opening_balance_minor=1000
    )
    db_session.flush()
    record_transaction(
        db_session,
        account_id=a.id,
        posted_date=date(2026, 5, 1),
        amount_minor=-1500,
        currency="GBP",
        payee="Tesco",
    )
    db_session.commit()

    update = _make_update()
    context = _make_context(deps)
    await h.balance_command(update, context)
    update.message.reply_text.assert_awaited_once()
    body = update.message.reply_text.call_args[0][0]
    assert "Wise GBP" in body
    assert "GBP" in body


async def test_summary_default_month(deps: h.BotDeps, db_session, monkeypatch) -> None:
    """`/summary` with no argument defaults to the current calendar month."""
    from datetime import date

    from finance.core.services import create_account, record_transaction

    today = date(2026, 5, 15)
    monkeypatch.setattr(h, "date", _FrozenDate(today))

    a = create_account(db_session, name="Wise GBP", currency="GBP")
    db_session.flush()
    record_transaction(
        db_session,
        account_id=a.id,
        posted_date=date(2026, 5, 1),
        amount_minor=300_000,
        currency="GBP",
        payee="Salary",
    )
    db_session.commit()

    update = _make_update()
    context = _make_context(deps)
    await h.summary_command(update, context)
    body = update.message.reply_text.call_args[0][0]
    assert "2026-05" in body
    assert "GBP" in body


async def test_summary_with_explicit_month(
    deps: h.BotDeps, db_session
) -> None:
    update = _make_update()
    context = _make_context(deps, args=["2026-04"])
    await h.summary_command(update, context)
    body = update.message.reply_text.call_args[0][0]
    assert "2026-04" in body or "No transactions" in body


async def test_drafts_empty(deps: h.BotDeps, db_session) -> None:
    update = _make_update()
    context = _make_context(deps)
    await h.drafts_command(update, context)
    body = update.message.reply_text.call_args[0][0]
    assert "No pending drafts" in body


# --- Document handler --------------------------------------------------------


async def test_document_handler_pdf_saves_and_prompts(
    deps: h.BotDeps, db_session, finance_home: Path
) -> None:
    from finance.core.services import create_account

    create_account(db_session, name="Wise EUR", currency="EUR")
    db_session.commit()

    fixture = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "wise"
        / "april_2026.pdf"
    )
    if not fixture.is_file():
        pytest.skip("wise fixture PDF not present")
    pdf_bytes = fixture.read_bytes()

    update = _make_update()
    update.message.document = MagicMock(
        mime_type="application/pdf",
        file_id="fake-file-id",
        file_name="april_2026.pdf",
    )
    context = _make_context(deps)
    fake_file = MagicMock()
    fake_file.download_as_bytearray = AsyncMock(return_value=bytearray(pdf_bytes))
    context.bot.get_file = AsyncMock(return_value=fake_file)

    await h.document_handler(update, context)

    update.message.reply_text.assert_awaited_once()
    body, kwargs = update.message.reply_text.call_args[0], update.message.reply_text.call_args[1]
    assert "PDF saved" in body[0]
    assert "reply_markup" in kwargs

    inbox = finance_home / "inbox"
    pdfs = list(inbox.glob("*.pdf"))
    assert len(pdfs) == 1
    state = context.user_data[h.USER_STATE_KEY]
    assert state["adapter_id"] is None
    assert state["account_id"] is None
    assert state["path"] == str(pdfs[0])


async def test_document_handler_non_pdf_declines(
    deps: h.BotDeps, db_session
) -> None:
    update = _make_update()
    update.message.document = MagicMock(
        mime_type="text/csv",
        file_id="csv-file-id",
        file_name="data.csv",
    )
    context = _make_context(deps)
    await h.document_handler(update, context)
    body = update.message.reply_text.call_args[0][0]
    assert "PDF" in body
    assert "csv" in body.lower() or "v1" in body


async def test_document_handler_idempotent_save(
    deps: h.BotDeps, finance_home: Path
) -> None:
    """Two saves of identical bytes should not duplicate the inbox file."""
    sample = b"%PDF-1.4\n" + b"A" * 256
    a1 = save_pdf_bytes(sample)
    a2 = save_pdf_bytes(sample)
    assert a1.path == a2.path
    assert a1.is_new
    assert not a2.is_new
    inbox = finance_home / "inbox"
    assert len(list(inbox.glob("*.pdf"))) == 1


# --- Callback flow (adapter + account picker) -------------------------------


async def test_callback_flow_runs_import(
    deps: h.BotDeps, db_session
) -> None:
    """Picking adapter then account triggers `import_artifact`."""
    from finance.core.services import create_account

    account = create_account(db_session, name="Wise EUR", currency="EUR")
    db_session.commit()

    fixture = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "wise"
        / "april_2026.pdf"
    )
    if not fixture.is_file():
        pytest.skip("wise fixture PDF not present")

    artifact = save_pdf_bytes(fixture.read_bytes())

    # Step 1: adapter selection
    update = _make_update()
    update.callback_query = MagicMock(
        data=f"{h.ADAPTER_PREFIX}wise-pdf",
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
    )
    context = _make_context(deps)
    context.user_data[h.USER_STATE_KEY] = {
        "path": str(artifact.path),
        "sha256": artifact.sha256,
        "adapter_id": None,
        "account_id": None,
    }
    await h.callback_handler(update, context)
    assert context.user_data[h.USER_STATE_KEY]["adapter_id"] == "wise-pdf"
    update.callback_query.edit_message_text.assert_awaited_once()

    # Step 2: account selection runs the import
    update2 = _make_update()
    update2.callback_query = MagicMock(
        data=f"{h.ACCOUNT_PREFIX}{account.id}",
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
    )
    await h.callback_handler(update2, context)
    update2.callback_query.edit_message_text.assert_awaited_once()
    body = update2.callback_query.edit_message_text.call_args[0][0]
    assert "Batch #" in body
    assert "drafts" in body
    assert h.USER_STATE_KEY not in context.user_data


# --- Build application + token redaction ------------------------------------


def test_build_application_refuses_empty_allow_list(db_path: Path) -> None:
    settings = Settings(
        db=DatabaseSettings(path=db_path),
        telegram=TelegramSettings(token=TOKEN, allow_list=[]),
    )
    with pytest.raises(EmptyAllowListError):
        build_application(settings)


def test_build_application_refuses_no_token(db_path: Path) -> None:
    settings = Settings(
        db=DatabaseSettings(path=db_path),
        telegram=TelegramSettings(token=None, allow_list=[ALLOWED_CHAT]),
    )
    with pytest.raises(RuntimeError):
        build_application(settings)


def test_build_application_returns_application(
    bot_settings: Settings, engine: Engine, bot_session_maker: sessionmaker
) -> None:
    app = build_application(
        bot_settings,
        registry=build_default_registry(),
        session_maker=bot_session_maker,
    )
    assert h.CTX_KEY in app.bot_data
    deps = app.bot_data[h.CTX_KEY]
    assert deps.allow_list.is_allowed(ALLOWED_CHAT)
    assert not deps.allow_list.is_allowed(DENIED_CHAT)


async def test_token_redacted_in_handler_logs(
    deps: h.BotDeps,
    bot_settings: Settings,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """No log line during a handler run contains the raw token."""
    redactor = configure_logging(bot_settings)
    log = logging.getLogger("finance.test.bot")
    log.addFilter(redactor)
    update = _make_update()
    context = _make_context(deps)
    with caplog.at_level(logging.DEBUG):
        log.info("starting with token=%s", TOKEN)
        await h.help_command(update, context)
    assert TOKEN not in caplog.text


# --- Helpers ---------------------------------------------------------------


class _FrozenDate:
    """Replacement for `datetime.date` whose `.today()` is deterministic."""

    def __init__(self, today_value):
        from datetime import date as _date

        self._today = today_value
        self._date = _date

    def today(self):
        return self._today

    def __call__(self, *args, **kwargs):
        return self._date(*args, **kwargs)
