"""Application settings.

Settings load from `~/.finance/config.toml` (or `FINANCE_HOME/config.toml`)
with environment-variable overrides via the `FINANCE_` prefix and `__` as the
nested-key delimiter (e.g., `FINANCE_API__KEY=…`).

Precedence (low → high): defaults < config file < environment variables.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from finance.core import paths


class DatabaseSettings(BaseModel):
    path: Path = Field(default_factory=paths.default_db_path)


class ApiSettings(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8000
    key: str | None = None


class TelegramSettings(BaseModel):
    token: str | None = None
    allow_list: list[int] = Field(default_factory=list)


class LogSettings(BaseModel):
    level: str = "INFO"


def _load_toml_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("rb") as f:
        return tomllib.load(f)


class Settings(BaseSettings):
    """Top-level application settings."""

    db: DatabaseSettings = Field(default_factory=DatabaseSettings)
    api: ApiSettings = Field(default_factory=ApiSettings)
    telegram: TelegramSettings = Field(default_factory=TelegramSettings)
    log: LogSettings = Field(default_factory=LogSettings)

    model_config = SettingsConfigDict(
        env_prefix="FINANCE_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # env > init (file) > defaults — the opposite of pydantic-settings' default,
        # so that values loaded from config.toml (passed in as init kwargs) are
        # overridden by FINANCE_* env vars.
        return (env_settings, init_settings, dotenv_settings, file_secret_settings)

    @classmethod
    def load(cls, config_file: Path | None = None) -> Settings:
        """Load settings: defaults <- config file <- env vars."""
        path = config_file or paths.config_path()
        file_data = _load_toml_file(path)
        # Pass file data as init kwargs; env vars (handled by pydantic-settings)
        # override per the source priority above.
        return cls(**file_data)
