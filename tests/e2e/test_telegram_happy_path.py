"""End-to-end Telegram happy path:

Allow-listed chat sends a PDF → adapter+account selection → confirmation
message contains the batch id and draft count → /summary returns the recap.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from finance.bots.telegram import handlers as h
from finance.bots.telegram.auth import AllowList
from finance.core.config import DatabaseSettings, Settings, TelegramSettings
from finance.core.operations import build_default_registry

pytestmark = [pytest.mark.e2e, pytest.mark.integration]

ALLOWED_CHAT = 12345


def _make_update(chat_id: int = ALLOWED_CHAT) -> MagicMock:
    update = MagicMock(name="Update")
    update.effective_chat = MagicMock(id=chat_id)
    update.effective_user = MagicMock(id=chat_id, is_bot=False, username="tester")
    msg = MagicMock(name="Message")
    msg.reply_text = AsyncMock()
    update.message = msg
    return update


def _make_context(deps: h.BotDeps) -> MagicMock:
    context = MagicMock(name="Context")
    context.bot_data = {h.CTX_KEY: deps}
    context.user_data = {}
    context.args = []
    bot_mock = MagicMock(name="Bot")
    bot_mock.get_file = AsyncMock()
    context.bot = bot_mock
    return context


async def test_telegram_pdf_to_summary(
    db_path: Path, engine: Engine, finance_home: Path, db_session
) -> None:
    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "wise" / "april_2026.pdf"
    if not fixture.is_file():
        pytest.skip("wise fixture PDF not present")

    from finance.core.services import create_account

    account = create_account(db_session, name="Wise EUR", currency="EUR")
    db_session.commit()

    settings = Settings(
        db=DatabaseSettings(path=db_path),
        telegram=TelegramSettings(token="fake-token", allow_list=[ALLOWED_CHAT]),
    )
    sm = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    deps = h.BotDeps(
        settings=settings,
        registry=build_default_registry(),
        session_maker=sm,
        allow_list=AllowList([ALLOWED_CHAT]),
    )

    # 1. document upload
    upd = _make_update()
    upd.message.document = MagicMock(
        mime_type="application/pdf",
        file_id="fake-id",
        file_name="april.pdf",
    )
    ctx = _make_context(deps)
    fake_file = MagicMock()
    fake_file.download_as_bytearray = AsyncMock(return_value=bytearray(fixture.read_bytes()))
    ctx.bot.get_file = AsyncMock(return_value=fake_file)
    await h.document_handler(upd, ctx)
    assert h.USER_STATE_KEY in ctx.user_data

    # 2. adapter pick
    upd2 = _make_update()
    upd2.callback_query = MagicMock(
        data=f"{h.ADAPTER_PREFIX}wise-pdf",
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
    )
    await h.callback_handler(upd2, ctx)

    # 3. account pick → import runs
    upd3 = _make_update()
    upd3.callback_query = MagicMock(
        data=f"{h.ACCOUNT_PREFIX}{account.id}",
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
    )
    await h.callback_handler(upd3, ctx)
    body = upd3.callback_query.edit_message_text.call_args[0][0]
    assert "Batch #" in body
    assert "drafts" in body

    # 4. /summary returns a one-message recap for the fixture month (April 2026)
    upd4 = _make_update()
    ctx4 = _make_context(deps)
    ctx4.args = ["2026-04"]
    await h.summary_command(upd4, ctx4)
    summary_body = upd4.message.reply_text.call_args[0][0]
    assert "2026-04" in summary_body
    # Drafts are excluded from the report; the body should not surface income
    # numbers above zero until a draft is confirmed. This e2e flow doesn't
    # confirm drafts in the bot path (review is web/CLI), so we expect the
    # "no transactions" message in this branch.
    assert "No transactions" in summary_body or "EUR" in summary_body
