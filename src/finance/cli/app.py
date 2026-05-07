"""Typer entrypoint: every command is a thin shell over `core.operations`.

The CLI never holds business logic. Each command parses arguments, builds an
operation input model, runs the operation through `_runtime.run_operation`,
and renders the output. The single exception is `init` (which creates the
DB file) and `config get/set` (which manages the local TOML config).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer

from finance.cli._runtime import (
    fail,
    get_registry,
    load_settings,
    print_json,
    read_toml,
    render_table,
    run_operation,
    write_secure_toml,
)
from finance.core import paths
from finance.core.secrets import redact

app = typer.Typer(
    name="finance",
    help="Local-first personal finance: ledger, ingestion, reports, surfaces.",
    no_args_is_help=True,
    add_completion=False,
)

account_app = typer.Typer(help="Manage accounts.", no_args_is_help=True)
transaction_app = typer.Typer(help="Record and list transactions.", no_args_is_help=True)
draft_app = typer.Typer(help="Review draft transactions from ingestion.", no_args_is_help=True)
report_app = typer.Typer(help="Reports (monthly summary, balances).", no_args_is_help=True)
config_app = typer.Typer(help="Get/set values in ~/.finance/config.toml.", no_args_is_help=True)

app.add_typer(account_app, name="account")
app.add_typer(transaction_app, name="transaction")
app.add_typer(draft_app, name="draft")
app.add_typer(report_app, name="report")
app.add_typer(config_app, name="config")


# --- Known config keys -------------------------------------------------------

# Keys whose values must be redacted on `config get` and never written verbatim
# to logs.
_SECRET_KEYS = frozenset({"api.key", "telegram.token"})

# All keys the CLI knows how to set from a string. The coercion column tells
# `config set` how to interpret the user's argument before writing TOML.
_KNOWN_KEYS: dict[str, str] = {
    "db.path": "str",
    "api.host": "str",
    "api.port": "int",
    "api.key": "str",
    "telegram.token": "str",
    "telegram.allow_list": "intlist",
    "log.level": "str",
}


def _split_dotted(key: str) -> list[str]:
    parts = key.split(".")
    if not all(parts):
        fail(f"malformed key {key!r}; expected dotted form like 'api.key'")
    return parts


def _get_nested(d: dict[str, Any], key: str) -> Any:
    parts = _split_dotted(key)
    cur: Any = d
    for p in parts:
        if not isinstance(cur, dict) or p not in cur:
            return None
        cur = cur[p]
    return cur


def _set_nested(d: dict[str, Any], key: str, value: Any) -> None:
    parts = _split_dotted(key)
    cur: dict[str, Any] = d
    for p in parts[:-1]:
        nxt = cur.get(p)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[p] = nxt
        cur = nxt
    cur[parts[-1]] = value


def _coerce(key: str, raw: str) -> Any:
    kind = _KNOWN_KEYS.get(key)
    if kind is None:
        fail(f"unknown config key {key!r}; known keys: {', '.join(sorted(_KNOWN_KEYS))}")
    if kind == "int":
        try:
            return int(raw)
        except ValueError:
            fail(f"value for {key} must be an integer; got {raw!r}")
    if kind == "intlist":
        if raw.strip() == "":
            return []
        try:
            return [int(p.strip()) for p in raw.split(",") if p.strip()]
        except ValueError:
            fail(f"value for {key} must be a comma-separated list of integers; got {raw!r}")
    return raw


# --- Account commands --------------------------------------------------------


@account_app.command("create")
def account_create(
    name: str = typer.Option(..., "--name", "-n", help="Human-readable account name."),
    currency: str = typer.Option(..., "--currency", "-c", help="3-letter ISO currency code."),
    opening_balance: int = typer.Option(
        0,
        "--opening-balance",
        help="Opening balance in integer minor units (default: 0).",
    ),
) -> None:
    """Create a new account."""
    registry = get_registry()
    op = registry.get("create_account")
    out = run_operation(
        op,
        {
            "name": name,
            "currency": currency,
            "opening_balance_minor": opening_balance,
        },
        load_settings(),
    )
    a = out.account
    typer.echo(
        f"created account #{a.id}: {a.name} ({a.currency}, opening {a.opening_balance_minor} minor)"
    )


@account_app.command("list")
def account_list(
    include_archived: bool = typer.Option(
        False, "--include-archived", help="Also list archived accounts."
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON instead of a table."),
) -> None:
    """List accounts."""
    registry = get_registry()
    op = registry.get("list_accounts")
    out = run_operation(op, {"include_archived": include_archived}, load_settings())
    rows = [
        {
            "id": a.id,
            "name": a.name,
            "currency": a.currency,
            "opening_minor": a.opening_balance_minor,
            "archived": a.archived,
        }
        for a in out.accounts
    ]
    if json_output:
        print_json([r for r in rows])
        return
    typer.echo(render_table(rows, ["id", "name", "currency", "opening_minor", "archived"]))


@account_app.command("archive")
def account_archive(
    account_id: int = typer.Option(..., "--id", help="Account id to archive."),
) -> None:
    """Archive (soft-delete) an account that has no transactions."""
    registry = get_registry()
    op = registry.get("archive_account")
    out = run_operation(op, {"account_id": account_id}, load_settings())
    typer.echo(f"archived account #{out.account.id}: {out.account.name}")


# --- Transaction commands ----------------------------------------------------


@transaction_app.command("add")
def transaction_add(
    account_id: int = typer.Option(..., "--account-id", help="Account id."),
    posted_date: str = typer.Option(..., "--date", help="Posted date as YYYY-MM-DD."),
    amount: int = typer.Option(
        ..., "--amount", help="Amount in integer minor units (negative = outflow)."
    ),
    currency: str = typer.Option(..., "--currency", help="3-letter ISO currency code."),
    payee: str = typer.Option(..., "--payee", help="Payee or description."),
    memo: str | None = typer.Option(None, "--memo", help="Optional memo."),
) -> None:
    """Record a transaction on an account."""
    registry = get_registry()
    op = registry.get("record_transaction")
    out = run_operation(
        op,
        {
            "account_id": account_id,
            "posted_date": posted_date,
            "amount_minor": amount,
            "currency": currency,
            "payee": payee,
            "memo": memo,
        },
        load_settings(),
    )
    t = out.transaction
    typer.echo(
        f"recorded transaction #{t.id}: {t.posted_date} {t.payee} {t.amount_minor} {t.currency}"
    )


@transaction_app.command("list")
def transaction_list(
    account_id: int = typer.Option(..., "--account-id", help="Account id."),
    start: str | None = typer.Option(None, "--start", help="Start date YYYY-MM-DD."),
    end: str | None = typer.Option(None, "--end", help="End date YYYY-MM-DD."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """List transactions on an account."""
    registry = get_registry()
    op = registry.get("list_transactions")
    out = run_operation(
        op,
        {"account_id": account_id, "start": start, "end": end},
        load_settings(),
    )
    rows = [
        {
            "id": t.id,
            "date": t.posted_date.isoformat(),
            "payee": t.payee,
            "amount_minor": t.amount_minor,
            "currency": t.currency,
        }
        for t in out.transactions
    ]
    if json_output:
        print_json(rows)
        return
    typer.echo(render_table(rows, ["id", "date", "payee", "amount_minor", "currency"]))


# --- Import command ----------------------------------------------------------


def _resolve_account_id(account: str) -> int:
    """Look up an account by id (numeric) or by exact name; fail if not found."""
    if account.isdigit():
        return int(account)
    registry = get_registry()
    op = registry.get("list_accounts")
    out = run_operation(op, {"include_archived": False}, load_settings())
    for a in out.accounts:
        if a.name == account:
            return int(a.id)
    fail(f"no active account named {account!r}")
    return 0  # unreachable; fail() raises


@app.command("import")
def import_cmd(
    adapter_id: str = typer.Argument(..., help="Adapter id, e.g. 'wise-pdf'."),
    path: Path = typer.Argument(..., help="Path to the source artifact (PDF)."),
    account: str = typer.Option(..., "--account", help="Target account name or numeric id."),
    force: bool = typer.Option(
        False,
        "--force",
        help="Re-ingest even if a batch with the same source sha256 already exists.",
    ),
) -> None:
    """Run an institution adapter against a file and persist drafts."""
    settings = load_settings()
    account_id = _resolve_account_id(account)
    registry = get_registry()
    op = registry.get("import_artifact")
    out = run_operation(
        op,
        {
            "adapter_id": adapter_id,
            "path": str(path),
            "account_id": account_id,
            "force": force,
        },
        settings,
    )
    typer.echo(
        f"batch #{out.batch_id}: {out.draft_count} draft(s) created "
        f"({out.duplicates_skipped} duplicate(s) skipped)"
    )


# --- Draft commands ----------------------------------------------------------


@draft_app.command("list")
def draft_list(
    account_id: int | None = typer.Option(None, "--account-id"),
    batch_id: int | None = typer.Option(None, "--batch-id"),
    status: str = typer.Option(
        "pending",
        "--status",
        help="One of: pending, confirmed, rejected. Pass 'all' to disable the filter.",
    ),
    limit: int | None = typer.Option(None, "--limit"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """List draft transactions."""
    registry = get_registry()
    op = registry.get("list_drafts")
    payload: dict[str, Any] = {
        "account_id": account_id,
        "batch_id": batch_id,
        "limit": limit,
    }
    if status == "all":
        payload["status"] = None
    else:
        payload["status"] = status
    out = run_operation(op, payload, load_settings())
    rows = [
        {
            "id": d.id,
            "date": d.posted_date.isoformat(),
            "account_id": d.account_id,
            "payee": d.payee,
            "amount_minor": d.amount_minor,
            "currency": d.currency,
            "status": d.status,
        }
        for d in out.drafts
    ]
    if json_output:
        print_json(rows)
        return
    typer.echo(
        render_table(
            rows,
            ["id", "date", "account_id", "payee", "amount_minor", "currency", "status"],
        )
    )


@draft_app.command("confirm")
def draft_confirm(
    draft_id: int = typer.Argument(..., help="Draft id to confirm."),
) -> None:
    """Promote a pending draft to a canonical transaction."""
    registry = get_registry()
    op = registry.get("confirm_draft")
    out = run_operation(op, {"draft_id": draft_id}, load_settings())
    typer.echo(f"confirmed draft #{out.draft_id} → transaction #{out.transaction.id}")


@draft_app.command("reject")
def draft_reject(
    draft_id: int = typer.Argument(..., help="Draft id to reject."),
) -> None:
    """Mark a pending draft as rejected."""
    registry = get_registry()
    op = registry.get("reject_draft")
    out = run_operation(op, {"draft_id": draft_id}, load_settings())
    typer.echo(f"rejected draft #{out.draft.id}")


# --- Report commands ---------------------------------------------------------


def _parse_year_month(arg: str) -> tuple[int, int]:
    parts = arg.split("-")
    if len(parts) != 2:
        fail(f"expected YYYY-MM, got {arg!r}")
    try:
        year = int(parts[0])
        month = int(parts[1])
    except ValueError:
        fail(f"expected YYYY-MM, got {arg!r}")
    if not (1 <= month <= 12):
        fail(f"month must be 1..12, got {month}")
    return year, month


@report_app.command("monthly")
def report_monthly(
    year_month: str = typer.Argument(..., help="Month as YYYY-MM, e.g. 2026-05."),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Print the monthly summary for the given calendar month."""
    year, month = _parse_year_month(year_month)
    registry = get_registry()
    op = registry.get("monthly_summary")
    out = run_operation(op, {"year": year, "month": month}, load_settings())

    if json_output:
        typer.echo(out.model_dump_json())
        return

    typer.echo(f"summary for {year:04d}-{month:02d}  ({out.start} → {out.end})")
    if not out.blocks:
        typer.echo("(no transactions in this month)")
        return
    rows = [
        {
            "currency": b.currency,
            "income_minor": b.income_minor,
            "expense_minor": b.expense_minor,
            "net_savings_minor": b.net_savings_minor,
            "savings_rate": "—" if b.savings_rate is None else f"{b.savings_rate}%",
            "tx_count": b.transaction_count,
        }
        for b in out.blocks
    ]
    typer.echo(
        render_table(
            rows,
            [
                "currency",
                "income_minor",
                "expense_minor",
                "net_savings_minor",
                "savings_rate",
                "tx_count",
            ],
        )
    )


# --- Config commands ---------------------------------------------------------


@config_app.command("get")
def config_get(
    key: str = typer.Argument(..., help="Dotted key, e.g. 'api.key'."),
) -> None:
    """Print the effective value of a config key (secrets are redacted)."""
    settings = load_settings()
    settings_dump = settings.model_dump(mode="json")
    value = _get_nested(settings_dump, key)
    if value is None:
        typer.echo(f"{key} = <unset>")
        return
    if key in _SECRET_KEYS:
        typer.echo(f"{key} = {redact(str(value))}")
        return
    typer.echo(f"{key} = {value}")


@config_app.command("set")
def config_set(
    key: str = typer.Argument(..., help="Dotted key, e.g. 'api.key'."),
    value: str = typer.Argument(..., help="Value to write (parsed by key type)."),
) -> None:
    """Set a config value in ~/.finance/config.toml (mode 0600)."""
    if key not in _KNOWN_KEYS:
        fail(f"unknown config key {key!r}; known keys: {', '.join(sorted(_KNOWN_KEYS))}")
    coerced = _coerce(key, value)
    config_path = paths.config_path()
    data = read_toml(config_path)
    _set_nested(data, key, coerced)
    write_secure_toml(config_path, data)
    if key in _SECRET_KEYS:
        typer.echo(f"set {key} (redacted)")
    else:
        typer.echo(f"set {key} = {coerced}")


# --- Top-level commands: init, serve, bot -----------------------------------


@app.command("init")
def init_cmd() -> None:
    """Create the database file and run all migrations to head."""
    from finance.core import db as core_db

    settings = load_settings()
    result = core_db.init_db(settings)
    typer.echo(f"db: {result['db_path']}")
    if result["migrations_applied"]:
        typer.echo(f"migrated {result['previous_revision']} → {result['current_revision']}")
    else:
        typer.echo(
            f"already initialized (revision {result['current_revision']}); no migrations applied"
        )


@app.command("serve")
def serve_cmd(
    host: str | None = typer.Option(None, "--host", help="Override api.host."),
    port: int | None = typer.Option(None, "--port", help="Override api.port."),
    with_ui: bool = typer.Option(
        False,
        "--with-ui",
        help="Mount the built web UI from src/finance/web/dist/ at /.",
    ),
) -> None:
    """Start the FastAPI app (REST + MCP)."""
    import uvicorn
    from fastapi.staticfiles import StaticFiles

    from finance.api.app import create_app
    from finance.core.logging import configure_logging

    settings = load_settings()
    if settings.api.key is None or settings.api.key == "":
        fail(
            "api.key is not set; run 'finance config set api.key <value>' first",
            code=2,
        )

    configure_logging(settings)
    app_obj = create_app(settings)

    if with_ui:
        dist = Path(__file__).resolve().parents[1] / "web" / "dist"
        if not dist.is_dir():
            fail(
                f"--with-ui set but {dist} does not exist; "
                "run 'npm run build' inside src/finance/web first"
            )
        app_obj.mount("/", StaticFiles(directory=str(dist), html=True), name="ui")

    uvicorn.run(
        app_obj,
        host=host or settings.api.host,
        port=port or settings.api.port,
        log_level=settings.log.level.lower(),
    )


@app.command("bot")
def bot_cmd() -> None:
    """Start the Telegram poller."""
    settings = load_settings()
    if not settings.telegram.allow_list:
        fail(
            "telegram.allow_list is empty; configure at least one chat id via "
            "'finance config set telegram.allow_list <chat_id>'",
            code=2,
        )
    if settings.telegram.token is None or settings.telegram.token == "":
        fail(
            "telegram.token is not set; run 'finance config set telegram.token <value>' first",
            code=2,
        )

    from finance.bots.telegram.app import build_application

    application = build_application(settings)
    application.run_polling(stop_signals=None)


def main() -> None:
    """Entry point used by the `finance` console script."""
    app()
