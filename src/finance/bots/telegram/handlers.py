"""Telegram handlers: thin wrappers that drive `core.operations`.

Every handler is deterministic — bare slash commands map 1:1 to registry
operations, and PDF uploads flow through `import_artifact`. There is NO LLM
or model call in this module; v1 is a deterministic dispatcher.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy.orm import sessionmaker
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import ContextTypes

from finance.bots.telegram.auth import AllowList, audit_rejected_chat
from finance.bots.telegram.inbox import save_pdf_bytes
from finance.core.config import Settings
from finance.core.money import Money
from finance.core.operations import OperationRegistry

logger = logging.getLogger(__name__)

CTX_KEY = "finance_context"
USER_STATE_KEY = "pending_import"

ADAPTER_PREFIX = "adapter:"
ACCOUNT_PREFIX = "account:"
HELP_TEXT = (
    "Commands:\n"
    "/help — show this message\n"
    "/balance — per-account balances\n"
    "/summary [YYYY-MM] — monthly summary (defaults to current month)\n"
    "/drafts — show up to 10 oldest pending drafts\n"
    "Or send a PDF statement as a document — I'll prompt for adapter and account."
)


@dataclass(frozen=True, slots=True)
class BotDeps:
    """Per-application dependencies (settings, ops, db). Stored on `bot_data`."""

    settings: Settings
    registry: OperationRegistry
    session_maker: sessionmaker[Any]
    allow_list: AllowList


def get_deps(context: ContextTypes.DEFAULT_TYPE) -> BotDeps:
    return context.bot_data[CTX_KEY]


def is_allowed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check the chat ID against the allow list; log+drop if not allowed."""
    chat = update.effective_chat
    deps = get_deps(context)
    chat_id = chat.id if chat is not None else None
    if not deps.allow_list.is_allowed(chat_id):
        audit_rejected_chat(chat_id)
        return False
    return True


def _run_op(
    deps: BotDeps,
    op_name: str,
    payload: dict[str, Any],
) -> Any:
    """Run an operation by name in a single committed session."""
    op = deps.registry.get(op_name)
    payload_model = op.input_model(**payload)
    session = deps.session_maker()
    try:
        result = op.callable(session, payload_model)
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# --- Slash commands ----------------------------------------------------------


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update, context):
        return
    assert update.message is not None
    await update.message.reply_text(HELP_TEXT)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Telegram convention; alias for `/help`."""
    await help_command(update, context)


async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update, context):
        return
    assert update.message is not None
    deps = get_deps(context)
    out = _run_op(deps, "account_balance_snapshot", {})
    if not out.accounts:
        await update.message.reply_text("No accounts.")
        return
    lines = [
        f"{row.name}: {Money(row.balance_minor, row.currency).format()}" for row in out.accounts
    ]
    await update.message.reply_text("\n".join(lines))


def _parse_year_month_arg(arg: str | None) -> tuple[int, int]:
    today = date.today()
    if arg is None:
        return today.year, today.month
    parts = arg.split("-")
    if len(parts) != 2:
        raise ValueError(f"expected YYYY-MM, got {arg!r}")
    year, month = int(parts[0]), int(parts[1])
    if not (1 <= month <= 12):
        raise ValueError(f"month must be 1..12, got {month}")
    return year, month


async def summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update, context):
        return
    assert update.message is not None
    arg: str | None = None
    if context.args:
        arg = context.args[0]
    try:
        year, month = _parse_year_month_arg(arg)
    except ValueError as exc:
        await update.message.reply_text(f"error: {exc}")
        return

    deps = get_deps(context)
    out = _run_op(deps, "monthly_summary", {"year": year, "month": month})
    if not out.blocks:
        await update.message.reply_text(f"No transactions in {year:04d}-{month:02d}.")
        return

    lines = [f"Summary for {year:04d}-{month:02d}"]
    for block in out.blocks:
        income = Money(block.income_minor, block.currency).format()
        expense = Money(block.expense_minor, block.currency).format()
        net = Money(block.net_savings_minor, block.currency).format()
        rate = "—" if block.savings_rate is None else f"{block.savings_rate}%"
        lines.append(
            f"{block.currency}: income {income}, expense {expense}, net {net}, savings rate {rate}"
        )
    await update.message.reply_text("\n".join(lines))


async def drafts_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update, context):
        return
    assert update.message is not None
    deps = get_deps(context)
    out = _run_op(
        deps,
        "list_drafts",
        {"status": "pending", "limit": 10},
    )
    if not out.drafts:
        await update.message.reply_text("No pending drafts.")
        return
    lines = ["Pending drafts (oldest 10):"]
    for d in out.drafts:
        money = Money(d.amount_minor, d.currency).format()
        lines.append(f"#{d.id} {d.posted_date} {d.payee} {money}")
    lines.append("Use the web UI or `finance draft confirm/reject <id>` to act on these.")
    await update.message.reply_text("\n".join(lines))


# --- Document handler --------------------------------------------------------


async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update, context):
        return
    msg = update.message
    assert msg is not None
    doc = msg.document
    assert doc is not None

    if (doc.mime_type or "").lower() != "application/pdf":
        await msg.reply_text(
            "v1 only accepts PDF statements. Use the CLI or web UI for other formats."
        )
        return

    # Download bytes; save to inbox before any further processing.
    file = await context.bot.get_file(doc.file_id)
    data = await file.download_as_bytearray()
    artifact = save_pdf_bytes(bytes(data))

    deps = get_deps(context)
    adapters = _run_op(deps, "list_adapters", {})
    accounts = _run_op(deps, "list_accounts", {"include_archived": False})

    if not accounts.accounts:
        await msg.reply_text(
            f"PDF saved to {artifact.path}, but no accounts exist yet. "
            "Create one with `finance account create` first."
        )
        return

    # Stash state for the callback flow.
    context.user_data[USER_STATE_KEY] = {  # type: ignore[index]
        "path": str(artifact.path),
        "sha256": artifact.sha256,
        "adapter_id": None,
        "account_id": None,
    }

    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(a.display_name, callback_data=f"{ADAPTER_PREFIX}{a.id}")]
            for a in adapters.adapters
        ]
    )
    await msg.reply_text(
        f"PDF saved ({'new' if artifact.is_new else 'duplicate of an earlier upload'}). "
        "Pick the institution adapter:",
        reply_markup=keyboard,
    )


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update, context):
        return
    query = update.callback_query
    assert query is not None
    await query.answer()
    data = query.data or ""
    deps = get_deps(context)
    state = context.user_data.get(USER_STATE_KEY) if context.user_data else None  # type: ignore[union-attr]
    if state is None:
        await query.edit_message_text(
            "I don't have an in-flight upload — please send the PDF again."
        )
        return

    if data.startswith(ADAPTER_PREFIX):
        adapter_id = data[len(ADAPTER_PREFIX) :]
        state["adapter_id"] = adapter_id
        accounts = _run_op(deps, "list_accounts", {"include_archived": False})
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        f"{a.name} ({a.currency})",
                        callback_data=f"{ACCOUNT_PREFIX}{a.id}",
                    )
                ]
                for a in accounts.accounts
            ]
        )
        await query.edit_message_text(
            f"Adapter: {adapter_id}. Now pick the target account:",
            reply_markup=keyboard,
        )
        return

    if data.startswith(ACCOUNT_PREFIX):
        try:
            account_id = int(data[len(ACCOUNT_PREFIX) :])
        except ValueError:
            await query.edit_message_text("error: malformed account selection")
            return
        state["account_id"] = account_id
        adapter_id = state.get("adapter_id")
        path = state.get("path")
        if adapter_id is None or path is None:
            await query.edit_message_text("Adapter not selected; please re-send the PDF.")
            return
        try:
            result = _run_op(
                deps,
                "import_artifact",
                {
                    "adapter_id": adapter_id,
                    "path": path,
                    "account_id": account_id,
                },
            )
        except Exception as exc:
            await query.edit_message_text(f"Import failed via {adapter_id}: {exc}")
            context.user_data.pop(USER_STATE_KEY, None)  # type: ignore[union-attr]
            return
        context.user_data.pop(USER_STATE_KEY, None)  # type: ignore[union-attr]
        await query.edit_message_text(
            f"Batch #{result.batch_id}: created {result.draft_count} drafts. Use /drafts to review."
        )
        return

    await query.edit_message_text(f"Unrecognized selection: {data!r}")


# Convenience for the CLI / tests: the list of adapters/accounts is small,
# so we deliberately load them on each PDF upload to stay in sync with state.
__all__ = [
    "ACCOUNT_PREFIX",
    "ADAPTER_PREFIX",
    "CTX_KEY",
    "HELP_TEXT",
    "USER_STATE_KEY",
    "BotDeps",
    "balance_command",
    "callback_handler",
    "document_handler",
    "drafts_command",
    "get_deps",
    "help_command",
    "is_allowed",
    "start_command",
    "summary_command",
]


def export_path(path: Path) -> str:
    """Return a string path for serialization in handler state."""
    return str(path)
