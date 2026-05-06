from __future__ import annotations

import stat
from pathlib import Path

import pytest

from finance.core import paths


def test_runtime_dir_uses_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "custom-home"
    monkeypatch.setenv(paths.ENV_VAR, str(target))
    result = paths.runtime_dir()
    assert result == target
    assert result.exists()


def test_runtime_dir_creates_with_mode_0700(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "fresh"
    monkeypatch.setenv(paths.ENV_VAR, str(target))
    paths.runtime_dir()
    mode = stat.S_IMODE(target.stat().st_mode)
    assert mode == 0o700


def test_default_db_path_lives_in_runtime_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "rt"
    monkeypatch.setenv(paths.ENV_VAR, str(target))
    assert paths.default_db_path() == target / "finance.db"
