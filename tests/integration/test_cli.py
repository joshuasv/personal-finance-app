"""Integration tests for the Typer CLI.

Each test runs against an isolated `FINANCE_HOME` (via the `finance_home`
fixture from conftest.py) so the CLI's reads/writes of `~/.finance/config.toml`
and the SQLite DB are sandboxed per test.
"""

from __future__ import annotations

import shutil
import tomllib
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from finance.cli.app import app

pytestmark = pytest.mark.integration


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def initialized(runner: CliRunner, finance_home: Path) -> Path:
    """A FINANCE_HOME with the DB migrated to head."""
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0, result.output
    return finance_home


def test_help_lists_all_subcommand_groups(runner: CliRunner) -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for group in (
        "account",
        "transaction",
        "import",
        "draft",
        "report",
        "serve",
        "bot",
        "init",
        "config",
    ):
        assert group in result.output


def test_init_creates_db(runner: CliRunner, finance_home: Path) -> None:
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0, result.output
    assert "migrated" in result.output or "already initialized" in result.output
    assert (finance_home / "finance.db").is_file()


def test_init_is_idempotent(runner: CliRunner, finance_home: Path) -> None:
    first = runner.invoke(app, ["init"])
    assert first.exit_code == 0
    second = runner.invoke(app, ["init"])
    assert second.exit_code == 0
    assert "already initialized" in second.output


def test_config_set_and_get_non_secret(runner: CliRunner, finance_home: Path) -> None:
    custom = finance_home / "custom.db"
    set_result = runner.invoke(app, ["config", "set", "db.path", str(custom)])
    assert set_result.exit_code == 0, set_result.output
    get_result = runner.invoke(app, ["config", "get", "db.path"])
    assert get_result.exit_code == 0
    assert str(custom) in get_result.output


def test_config_set_secret_redacts_on_get(runner: CliRunner, finance_home: Path) -> None:
    secret = "sk_live_abcdef0123456789"
    set_result = runner.invoke(app, ["config", "set", "api.key", secret])
    assert set_result.exit_code == 0
    assert secret not in set_result.output  # set output redacted
    get_result = runner.invoke(app, ["config", "get", "api.key"])
    assert get_result.exit_code == 0
    assert secret not in get_result.output
    assert "chars)" in get_result.output  # length indicator from `redact`


def test_config_file_has_0600_permissions(runner: CliRunner, finance_home: Path) -> None:
    set_result = runner.invoke(app, ["config", "set", "api.key", "anything"])
    assert set_result.exit_code == 0
    cfg = finance_home / "config.toml"
    assert cfg.is_file()
    mode = cfg.stat().st_mode & 0o777
    assert mode == 0o600, oct(mode)


def test_config_set_telegram_allow_list_is_intlist(runner: CliRunner, finance_home: Path) -> None:
    result = runner.invoke(app, ["config", "set", "telegram.allow_list", "12345,67890"])
    assert result.exit_code == 0
    cfg = finance_home / "config.toml"
    with cfg.open("rb") as f:
        data = tomllib.load(f)
    assert data["telegram"]["allow_list"] == [12345, 67890]


def test_config_set_unknown_key_fails(runner: CliRunner, finance_home: Path) -> None:
    result = runner.invoke(app, ["config", "set", "made.up.key", "x"])
    assert result.exit_code != 0
    assert "unknown config key" in result.output


def test_account_create_and_list(runner: CliRunner, initialized: Path) -> None:
    create = runner.invoke(app, ["account", "create", "--name", "Wise GBP", "--currency", "GBP"])
    assert create.exit_code == 0, create.output
    assert "Wise GBP" in create.output

    listed = runner.invoke(app, ["account", "list"])
    assert listed.exit_code == 0
    assert "Wise GBP" in listed.output


def test_account_create_duplicate_returns_error(runner: CliRunner, initialized: Path) -> None:
    args = ["account", "create", "--name", "Wise GBP", "--currency", "GBP"]
    first = runner.invoke(app, args)
    assert first.exit_code == 0
    second = runner.invoke(app, args)
    assert second.exit_code != 0
    assert "already exists" in second.output


def test_account_archive(runner: CliRunner, initialized: Path) -> None:
    runner.invoke(app, ["account", "create", "--name", "Tmp", "--currency", "GBP"])
    listed = runner.invoke(app, ["account", "list", "--json"])
    import json as _json

    rows = _json.loads(listed.output)
    account_id = next(r["id"] for r in rows if r["name"] == "Tmp")
    archive = runner.invoke(app, ["account", "archive", "--id", str(account_id)])
    assert archive.exit_code == 0
    assert "archived" in archive.output


def test_transaction_add_and_list(runner: CliRunner, initialized: Path) -> None:
    runner.invoke(app, ["account", "create", "--name", "Wise GBP", "--currency", "GBP"])
    listed = runner.invoke(app, ["account", "list", "--json"])
    import json as _json

    account_id = _json.loads(listed.output)[0]["id"]

    add = runner.invoke(
        app,
        [
            "transaction",
            "add",
            "--account-id",
            str(account_id),
            "--date",
            "2026-05-01",
            "--amount",
            "-1250",
            "--currency",
            "GBP",
            "--payee",
            "Tesco",
        ],
    )
    assert add.exit_code == 0, add.output

    txs = runner.invoke(app, ["transaction", "list", "--account-id", str(account_id)])
    assert txs.exit_code == 0
    assert "Tesco" in txs.output


def test_import_unknown_adapter_fails_with_listing(
    runner: CliRunner, initialized: Path, tmp_path: Path
) -> None:
    runner.invoke(app, ["account", "create", "--name", "Wise GBP", "--currency", "GBP"])
    fake_pdf = tmp_path / "fake.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3")
    result = runner.invoke(
        app,
        [
            "import",
            "madeup-adapter",
            str(fake_pdf),
            "--account",
            "Wise GBP",
        ],
    )
    assert result.exit_code != 0
    assert "wise-pdf" in result.output  # listing the known adapters


def test_import_wise_pdf_creates_drafts(
    runner: CliRunner, initialized: Path, tmp_path: Path
) -> None:
    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "wise" / "april_2026.pdf"
    if not fixture.is_file():
        pytest.skip("wise fixture PDF not present")
    runner.invoke(app, ["account", "create", "--name", "Wise EUR", "--currency", "EUR"])
    work = tmp_path / "april.pdf"
    shutil.copy(fixture, work)
    result = runner.invoke(app, ["import", "wise-pdf", str(work), "--account", "Wise EUR"])
    assert result.exit_code == 0, result.output
    assert "draft(s) created" in result.output


def test_draft_list_pending_and_confirm_flow(
    runner: CliRunner, initialized: Path, tmp_path: Path
) -> None:
    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "wise" / "april_2026.pdf"
    if not fixture.is_file():
        pytest.skip("wise fixture PDF not present")
    runner.invoke(app, ["account", "create", "--name", "Wise EUR", "--currency", "EUR"])
    work = tmp_path / "april.pdf"
    shutil.copy(fixture, work)
    runner.invoke(app, ["import", "wise-pdf", str(work), "--account", "Wise EUR"])

    listed = runner.invoke(app, ["draft", "list", "--status", "pending", "--json"])
    assert listed.exit_code == 0
    import json as _json

    rows = _json.loads(listed.output)
    assert rows, "expected at least one pending draft"

    first_id = rows[0]["id"]
    confirmed = runner.invoke(app, ["draft", "confirm", str(first_id)])
    assert confirmed.exit_code == 0, confirmed.output
    assert "confirmed draft" in confirmed.output


def test_report_monthly_table_and_json(runner: CliRunner, initialized: Path) -> None:
    runner.invoke(app, ["account", "create", "--name", "Wise GBP", "--currency", "GBP"])
    listed = runner.invoke(app, ["account", "list", "--json"])
    import json as _json

    account_id = _json.loads(listed.output)[0]["id"]
    runner.invoke(
        app,
        [
            "transaction",
            "add",
            "--account-id",
            str(account_id),
            "--date",
            "2026-05-01",
            "--amount",
            "-1250",
            "--currency",
            "GBP",
            "--payee",
            "Tesco",
        ],
    )
    runner.invoke(
        app,
        [
            "transaction",
            "add",
            "--account-id",
            str(account_id),
            "--date",
            "2026-05-15",
            "--amount",
            "300000",
            "--currency",
            "GBP",
            "--payee",
            "Salary",
        ],
    )

    table = runner.invoke(app, ["report", "monthly", "2026-05"])
    assert table.exit_code == 0, table.output
    assert "GBP" in table.output

    js = runner.invoke(app, ["report", "monthly", "2026-05", "--json"])
    assert js.exit_code == 0
    payload = _json.loads(js.output)
    assert payload["year"] == 2026
    assert payload["month"] == 5
    blocks = payload["blocks"]
    assert any(b["currency"] == "GBP" for b in blocks)


def test_report_monthly_invalid_month(runner: CliRunner, initialized: Path) -> None:
    result = runner.invoke(app, ["report", "monthly", "2026-13"])
    assert result.exit_code != 0


def test_bot_refuses_with_empty_allow_list(runner: CliRunner, finance_home: Path) -> None:
    """`finance bot` must fail-closed when telegram.allow_list is empty."""
    runner.invoke(app, ["config", "set", "telegram.token", "fake-token"])
    result = runner.invoke(app, ["bot"])
    assert result.exit_code != 0
    assert "allow_list" in result.output


def test_bot_configures_logging_before_polling(
    runner: CliRunner, finance_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`finance bot` MUST call `configure_logging(settings)` before
    `Application.run_polling(...)` so the operator's terminal isn't silent.

    Mirrors `serve_cmd`'s pattern: the CLI command owns logging setup, not
    the bot module.
    """
    runner.invoke(app, ["config", "set", "telegram.token", "fake-token"])
    runner.invoke(app, ["config", "set", "telegram.allow_list", "12345"])

    call_order: list[str] = []
    from finance.bots.telegram import app as bot_app
    from finance.core import logging as core_logging

    real_configure_logging = core_logging.configure_logging

    def tracking_configure_logging(*args: Any, **kwargs: Any) -> Any:
        call_order.append("configure_logging")
        return real_configure_logging(*args, **kwargs)

    def tracking_build_application(*args: Any, **kwargs: Any) -> Any:
        call_order.append("build_application")

        # Return an object whose run_polling raises immediately so we don't
        # actually hit api.telegram.org.
        class _StubApp:
            def run_polling(self_inner, **_: Any) -> None:
                call_order.append("run_polling")
                raise RuntimeError("stop here in test")

        return _StubApp()

    monkeypatch.setattr(core_logging, "configure_logging", tracking_configure_logging)
    monkeypatch.setattr(bot_app, "build_application", tracking_build_application)

    result = runner.invoke(app, ["bot"])
    assert result.exit_code != 0  # the stub run_polling raises

    assert call_order[:3] == ["configure_logging", "build_application", "run_polling"], (
        f"expected configure_logging before build_application before run_polling; got {call_order}"
    )


def test_serve_refuses_without_api_key(runner: CliRunner, finance_home: Path) -> None:
    result = runner.invoke(app, ["serve"])
    assert result.exit_code != 0
    assert "api.key" in result.output
