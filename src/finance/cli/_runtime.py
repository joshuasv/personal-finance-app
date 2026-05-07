"""Shared CLI runtime helpers: settings load, session scope, error printing."""

from __future__ import annotations

import json
import sys
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import typer
from sqlalchemy.orm import Session

from finance.core import db as core_db
from finance.core.config import Settings
from finance.core.operations import Operation, OperationRegistry, build_default_registry
from finance.core.services.errors import DomainError
from finance.ingestion.protocols import AdapterParseError


def load_settings() -> Settings:
    return Settings.load()


@contextmanager
def cli_session(settings: Settings) -> Generator[Session, None, None]:
    """Open a session against the configured DB and commit on success."""
    engine = core_db.engine_for(settings.db.path)
    factory = core_db.session_factory_for(engine)
    with core_db.session_scope(factory) as session:
        yield session


def get_registry() -> OperationRegistry:
    return build_default_registry()


def run_operation(op: Operation, payload_dict: dict[str, Any], settings: Settings) -> Any:
    """Validate the payload, run the operation, and return the model result.

    Domain errors and adapter parse failures abort the CLI with exit code 1.
    """
    try:
        payload = op.input_model(**payload_dict)
    except Exception as exc:
        typer.echo(f"error: invalid input — {exc}", err=True)
        raise typer.Exit(code=2) from exc

    try:
        with cli_session(settings) as session:
            result = op.callable(session, payload)
    except (DomainError, AdapterParseError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    return result


def print_json(obj: Any) -> None:
    typer.echo(json.dumps(obj, default=str, indent=2, sort_keys=True))


def render_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    """Tiny tabular renderer — no third-party dep, monospace-friendly output."""
    if not rows:
        return "(no rows)"
    widths = {c: max(len(c), max(len(str(r.get(c, ""))) for r in rows)) for c in columns}
    header = "  ".join(c.ljust(widths[c]) for c in columns)
    sep = "  ".join("-" * widths[c] for c in columns)
    body = "\n".join("  ".join(str(r.get(c, "")).ljust(widths[c]) for c in columns) for r in rows)
    return f"{header}\n{sep}\n{body}"


def fail(msg: str, code: int = 1) -> None:
    typer.echo(f"error: {msg}", err=True)
    raise typer.Exit(code=code)


def write_secure_toml(path: Path, data: dict[str, Any]) -> None:
    """Write TOML and ensure the file mode is 0600."""
    import tomli_w

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(tomli_w.dumps(data).encode("utf-8"))
    path.chmod(0o600)


def read_toml(path: Path) -> dict[str, Any]:
    import tomllib

    if not path.exists():
        return {}
    with path.open("rb") as f:
        return tomllib.load(f)


def stderr_print(msg: str) -> None:
    print(msg, file=sys.stderr)
