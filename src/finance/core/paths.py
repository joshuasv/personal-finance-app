"""Filesystem layout for the app's runtime directory.

The runtime dir defaults to `~/.finance/` and can be overridden by the
`FINANCE_HOME` environment variable. The directory is created on first
use with mode 0700 so the SQLite DB and config file (which holds secrets)
are not world-readable.
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_VAR = "FINANCE_HOME"
DEFAULT_DIRNAME = ".finance"


def runtime_dir() -> Path:
    """Return the runtime directory, creating it (mode 0700) if missing."""
    override = os.environ.get(ENV_VAR)
    path = Path(override).expanduser() if override else Path.home() / DEFAULT_DIRNAME
    if not path.exists():
        path.mkdir(parents=True, mode=0o700)
    return path


def config_path() -> Path:
    """Path to the TOML config file."""
    return runtime_dir() / "config.toml"


def default_db_path() -> Path:
    """Default location for the SQLite database."""
    return runtime_dir() / "finance.db"
