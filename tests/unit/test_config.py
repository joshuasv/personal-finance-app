from __future__ import annotations

from pathlib import Path

import pytest

from finance.core.config import Settings


def _write_config(home: Path, body: str) -> Path:
    cfg = home / "config.toml"
    cfg.write_text(body)
    return cfg


def test_defaults_when_no_file(finance_home: Path) -> None:
    s = Settings.load()
    assert s.api.host == "127.0.0.1"
    assert s.api.port == 8000
    assert s.api.key is None
    assert s.telegram.token is None
    assert s.telegram.allow_list == []
    assert s.log.level == "INFO"


def test_file_overrides_defaults(finance_home: Path) -> None:
    _write_config(
        finance_home,
        """
        [api]
        host = "0.0.0.0"
        port = 9000
        key = "from-file"

        [telegram]
        token = "tg-token"
        allow_list = [11, 22]

        [log]
        level = "DEBUG"
        """,
    )
    s = Settings.load()
    assert s.api.host == "0.0.0.0"
    assert s.api.port == 9000
    assert s.api.key == "from-file"
    assert s.telegram.token == "tg-token"
    assert s.telegram.allow_list == [11, 22]
    assert s.log.level == "DEBUG"


def test_env_overrides_file(finance_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_config(
        finance_home,
        """
        [api]
        key = "from-file"
        """,
    )
    monkeypatch.setenv("FINANCE_API__KEY", "from-env")
    s = Settings.load()
    assert s.api.key == "from-env"
