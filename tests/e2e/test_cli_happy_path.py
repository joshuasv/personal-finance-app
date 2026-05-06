"""End-to-end happy path: init → account → import → drafts → confirm → report.

Drives the entire ledger pipeline through the Typer CLI, the way a user would.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from finance.cli.app import app

pytestmark = [pytest.mark.e2e, pytest.mark.integration]


def test_full_cli_happy_path(
    runner_for_test: CliRunner, finance_home: Path, tmp_path: Path
) -> None:
    fixture = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "wise"
        / "april_2026.pdf"
    )
    if not fixture.is_file():
        pytest.skip("wise fixture PDF not present")

    runner = runner_for_test

    # 1. init
    init = runner.invoke(app, ["init"])
    assert init.exit_code == 0, init.output

    # 2. create account
    create = runner.invoke(
        app, ["account", "create", "--name", "Wise EUR", "--currency", "EUR"]
    )
    assert create.exit_code == 0, create.output

    # 3. import the Wise PDF
    work = tmp_path / "april.pdf"
    shutil.copy(fixture, work)
    imp = runner.invoke(
        app, ["import", "wise-pdf", str(work), "--account", "Wise EUR"]
    )
    assert imp.exit_code == 0, imp.output
    assert "draft(s) created" in imp.output

    # 4. list pending drafts → expect ≥ 1
    listed = runner.invoke(app, ["draft", "list", "--status", "pending", "--json"])
    assert listed.exit_code == 0
    rows = json.loads(listed.output)
    assert len(rows) >= 1

    # 5. confirm every pending draft
    for r in rows:
        confirmed = runner.invoke(app, ["draft", "confirm", str(r["id"])])
        assert confirmed.exit_code == 0, confirmed.output

    # 6. monthly summary shows non-zero activity in April 2026 (the fixture month)
    summary = runner.invoke(app, ["report", "monthly", "2026-04", "--json"])
    assert summary.exit_code == 0, summary.output
    payload = json.loads(summary.output)
    assert payload["year"] == 2026
    assert payload["month"] == 4
    assert payload["blocks"], "expected at least one summary block for April 2026"
    block = payload["blocks"][0]
    assert block["currency"] == "EUR"
    assert block["transaction_count"] >= 1


@pytest.fixture
def runner_for_test() -> CliRunner:
    return CliRunner()
