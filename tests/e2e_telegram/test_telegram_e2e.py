"""Real-Telegram E2E tests.

These tests drive a Telethon user-account client against a real `finance bot`
subprocess against the real Telegram servers. They exercise *exactly* the
same code path a human user hits, including:

  - the `finance bot` CLI command (binary on PATH, env-driven config)
  - `configure_logging` + `build_application` startup
  - `Application.run_polling(...)` with the Telegram updater
  - real getUpdates long-poll + outbound sendMessage / editMessageText
  - real file download from Telegram's CDN for PDF uploads

If `finance bot` exits silently (the bug Joshua hit manually on
2026-05-08), `bot_process`'s "bot ready" wait fails and the captured
stdout/stderr is attached to the failure message — making the silent
failure loud.

Marker: `@pytest.mark.e2e_telegram` — skipped by default. Run with
`pytest -m e2e_telegram` once `.telegram-test-secrets.toml` and the
`FINANCE_E2E_BOT_*` env vars are set.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.e2e_telegram


# --- Sanity: bot stays alive and emits a startup line -----------------------


async def test_when_bot_starts_then_terminal_is_not_silent(
    bot_process: tuple[subprocess.Popen[bytes], Path],
    bot_log_tail: Any,
) -> None:
    """The "no log output at all" symptom from the original bug report
    becomes a deterministic test failure: if `bot ready` doesn't show up
    within 30s, the `bot_process` fixture itself fails. Reaching this test
    body proves the launching terminal is not silent."""
    proc, _ = bot_process
    assert proc.poll() is None, f"bot exited unexpectedly during startup. Tail:\n{bot_log_tail()}"
    log = bot_log_tail()
    assert "bot ready" in log, f"expected 'bot ready' in log; got:\n{log}"


# --- /help via real Telegram dispatcher --------------------------------------


async def test_when_user_sends_help_then_bot_replies_with_commands_list(
    bot_process: tuple[subprocess.Popen[bytes], Path],
    tg_client: Any,
    e2e_creds: dict[str, Any],
    bot_log_tail: Any,
) -> None:
    bot = e2e_creds["bot_username"]
    async with tg_client.conversation(bot, timeout=20) as conv:
        await conv.send_message("/help")
        reply = await conv.get_response()

    assert "Commands" in (reply.text or ""), (
        f"unexpected /help reply: {reply.text!r}\n--- bot log tail ---\n{bot_log_tail()}"
    )


# --- /balance on a fresh DB -------------------------------------------------


async def test_when_user_sends_balance_then_bot_lists_seeded_account(
    bot_process: tuple[subprocess.Popen[bytes], Path],
    tg_client: Any,
    e2e_creds: dict[str, Any],
    bot_log_tail: Any,
) -> None:
    """`bot_process` seeds one account ("E2E Test EUR") before starting.
    The /balance reply should mention it."""
    bot = e2e_creds["bot_username"]
    async with tg_client.conversation(bot, timeout=20) as conv:
        await conv.send_message("/balance")
        reply = await conv.get_response()

    assert "E2E Test EUR" in (reply.text or ""), (
        f"unexpected /balance reply: {reply.text!r}\n--- bot log tail ---\n{bot_log_tail()}"
    )


# --- /drafts on a fresh DB --------------------------------------------------


async def test_when_user_sends_drafts_on_fresh_db_then_bot_says_no_drafts(
    bot_process: tuple[subprocess.Popen[bytes], Path],
    tg_client: Any,
    e2e_creds: dict[str, Any],
    bot_log_tail: Any,
) -> None:
    bot = e2e_creds["bot_username"]
    async with tg_client.conversation(bot, timeout=20) as conv:
        await conv.send_message("/drafts")
        reply = await conv.get_response()

    assert "No pending drafts" in (reply.text or ""), (
        f"unexpected /drafts reply: {reply.text!r}\n--- bot log tail ---\n{bot_log_tail()}"
    )


# --- Full PDF-upload flow ---------------------------------------------------


async def test_when_user_uploads_pdf_then_bot_walks_through_picker_to_drafts(
    bot_process: tuple[subprocess.Popen[bytes], Path],
    tg_client: Any,
    e2e_creds: dict[str, Any],
    wise_pdf: Path,
    bot_log_tail: Any,
) -> None:
    """Send a real Wise PDF as a document → adapter picker → account picker →
    "Batch #N: M drafts". This is the user-visible happy path that the
    Level-1 / Level-2 tests can't exercise end-to-end."""
    bot = e2e_creds["bot_username"]

    async with tg_client.conversation(bot, timeout=60) as conv:
        await conv.send_file(str(wise_pdf), force_document=True)

        adapter_picker = await conv.get_response()
        assert "PDF saved" in (adapter_picker.text or ""), (
            f"expected 'PDF saved' picker prompt; got: {adapter_picker.text!r}\n"
            f"--- bot log tail ---\n{bot_log_tail()}"
        )
        assert adapter_picker.buttons is not None, "expected adapter inline keyboard"

        # Click the first adapter (wise-pdf is the only one in v1).
        await adapter_picker.click(0)

        # The same message gets edited with the account picker.
        account_picker = await conv.get_edit()
        assert account_picker.buttons is not None, "expected account inline keyboard"

        # Click the first account ("E2E Test EUR" was seeded by bot_process).
        await account_picker.click(0)

        final = await conv.get_edit()
        body = final.text or ""

    assert "Batch #" in body and "drafts" in body, (
        f"expected 'Batch #N ... drafts' final message; got: {body!r}\n"
        f"--- bot log tail ---\n{bot_log_tail()}"
    )
