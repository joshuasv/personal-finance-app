## MODIFIED Requirements

### Requirement: Serve and bot commands
The system SHALL provide `finance serve` which starts the FastAPI app (REST + MCP) and `finance bot` which starts the Telegram poller. Both SHALL read configuration from `~/.finance/config.toml`. **Both SHALL configure logging via `core.logging.configure_logging(settings)` before starting their respective server/poller**, so that operators see startup, handler-registration, and error log output in the launching terminal. `finance serve --with-ui` SHALL additionally mount the built web UI at `/`.

#### Scenario: Serve starts on configured port
- **WHEN** the user runs `finance serve` with `api.host=127.0.0.1` and `api.port=8000`
- **THEN** the process listens on `127.0.0.1:8000` and `GET /health` returns `200`

#### Scenario: Bot refuses to start without an allow-list
- **WHEN** the user runs `finance bot` and `telegram.allow_list` is empty
- **THEN** the command exits non-zero with a message instructing the user to set `telegram.allow_list`

#### Scenario: Bot configures logging before polling
- **GIVEN** a valid `telegram.token` and a non-empty `telegram.allow_list`
- **WHEN** the user runs `finance bot`
- **THEN** `configure_logging(settings)` is invoked before `Application.run_polling(...)`, the root logger has a handler attached at the configured level, and operator-visible log output appears in the launching terminal during startup
