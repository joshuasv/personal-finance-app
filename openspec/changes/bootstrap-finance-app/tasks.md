## 1. Repo & tooling setup

- [x] 1.1 Initialize Python project with `uv` (`pyproject.toml`, `uv.lock`), Python 3.12 pinned
- [x] 1.2 Add runtime deps: `fastapi`, `uvicorn[standard]`, `typer`, `sqlalchemy>=2`, `alembic`, `pydantic>=2`, `pydantic-settings`, `pdfplumber`, `python-telegram-bot`, `mcp` (official Python SDK), `httpx`, `tomli-w`
- [x] 1.3 Add dev deps: `ruff`, `mypy`, `pytest`, `pytest-asyncio`, `pytest-cov`, `httpx` (test client), `respx`
- [x] 1.4 Configure `ruff` (lint + format) and `mypy` (strict on `src/finance/core`) in `pyproject.toml`
- [x] 1.5 Add `Makefile` (or `justfile`) targets: `fmt`, `lint`, `typecheck`, `test`, `run-api`, `run-bot`, `run-web`
- [x] 1.6 Add `.gitignore` entries for `.venv/`, `__pycache__/`, `node_modules/`, `dist/`, `.coverage`, `~/.finance` is irrelevant (outside repo)
- [x] 1.7 Create initial package layout: `src/finance/{core,ingestion,reporting,api,mcp,cli,bots/telegram,web}` each with `__init__.py`
- [x] 1.8 Add `tests/{unit,integration,fixtures}` with `conftest.py` providing a function-scoped temp SQLite engine

## 2. Configuration & paths

- [x] 2.1 Implement `core.config.Settings` (pydantic-settings) loading from `~/.finance/config.toml` and env overrides; fields: `db.path`, `api.host`, `api.port`, `api.key`, `telegram.token`, `telegram.allow_list`, `log.level`
- [x] 2.2 Implement `core.paths` to resolve `~/.finance/` (with override via env), creating the directory on first use with mode `0700`
- [x] 2.3 Unit-test config load: missing file returns sane defaults, file values override defaults, env overrides file
- [x] 2.4 Implement secret redaction helper (`redact("sk_live_abcdef…", keep=8)`) used by CLI `config get`

## 3. Database, models, migrations

- [x] 3.1 Implement `core.db.engine_for(path)` building a SQLAlchemy 2.x engine (SQLite, WAL on, foreign keys on)
- [x] 3.2 Implement `core.db.session_scope()` context manager (commit/rollback/close)
- [x] 3.3 Define ORM models in `core.models`: `Account`, `Transaction`, `IngestionBatch`, `DraftTransaction`
- [x] 3.4 Add Alembic; configure to read `db.path` from settings
- [x] 3.5 Write the v1 baseline migration covering all tables and indexes
- [x] 3.6 Implement `core.db.init_db()` that runs migrations to head idempotently
- [x] 3.7 Integration test: `init_db` against a fresh path creates the schema; running it twice is a no-op

## 4. Money & validation primitives

- [x] 4.1 Implement `core.money.Money` (currency + integer minor units) with format/parse helpers
- [x] 4.2 Implement Pydantic validators that reject float amounts at API/CLI boundaries (`Field(strict=True)` int, custom validator with helpful message)
- [x] 4.3 Unit-test: float amount in JSON request fails with the documented error; integer amount succeeds

## 5. Ledger-core operations

- [x] 5.1 Implement repositories in `core.repositories` (`accounts`, `transactions`) — pure CRUD over the session
- [x] 5.2 Implement services in `core.services`: `create_account`, `archive_account`, `record_transaction`, `update_transaction`, `delete_transaction`, `account_balance`, `list_transactions`
- [x] 5.3 Enforce invariants in services: unique active account names, currency matches account, non-zero amount, ISO currency
- [x] 5.4 Unit-test every service against in-memory SQLite covering all spec scenarios in `ledger-core/spec.md`
- [x] 5.5 Property-test `account_balance`: balance equals opening + Σ amounts for randomized transaction sets
- [x] 5.6 Drop the `account.type` enum: remove `AccountType` from `core.models`, `core.services.accounts`, `core.operations.models`, the baseline migration, and tests; the Account model carries no type field in v1 (future net-worth change introduces `is_liability` instead)

## 6. Operation registry & Pydantic IO models

- [x] 6.1 Define `core.operations.Operation` (name, input_model, output_model, callable, description, tags)
- [x] 6.2 Implement `core.operations.registry` with `register()`, `get()`, `all()`
- [x] 6.3 Define input/output Pydantic models for every service from §5 in `core.operations.models`
- [x] 6.4 Wrap each service as a registered `Operation` (factory pattern in `core.operations.bootstrap.register_all()`)
- [x] 6.5 Unit-test: registry contains the expected operation names; each operation's input model rejects invalid payloads with field-level errors

## 7. Statement ingestion

- [x] 7.1 Define `ingestion.protocols.InstitutionAdapter` (id, display_name, source_artifact_type, `parse(path, account) -> Iterable[DraftTransaction]`)
- [x] 7.2 Implement `ingestion.registry` for adapters (`register_adapter`, `get_adapter`, `list_adapters`)
- [x] 7.3 Implement `ingestion.wise_pdf.WiseStatementAdapter` using `pdfplumber`; extract date, payee/description, amount (sign-correct), currency
- [x] 7.4 Bundle 2–3 fixture Wise PDFs in `tests/fixtures/wise/` covering at least: a clean month, a month with reversals/refunds, an edge case (multi-page)
- [x] 7.5 Implement `ingestion.pipeline.import_artifact(adapter_id, path, account_id)`: creates `IngestionBatch`, dedups within batch by content hash, persists drafts as `pending`
- [x] 7.6 Implement `ingestion.review`: `confirm_draft(draft_id)` (creates a `Transaction`, marks draft `confirmed`, refuses on duplicate content hash for same account), `reject_draft(draft_id)`
- [x] 7.7 Detect re-uploads: when an `IngestionBatch` already exists with the source's sha256, return a "already ingested" warning unless explicit `force=True`
- [x] 7.8 Register `import_artifact`, `list_drafts`, `confirm_draft`, `reject_draft`, `list_adapters` as operations
- [x] 7.9 Integration tests covering every scenario in `statement-ingestion/spec.md`, including parser-failure error shape and currency-mismatch refusal

## 8. Reporting

- [x] 8.1 Implement `reporting.queries.income_expense_for_month(year, month, currency)` returning income, expense, net savings, savings rate
- [x] 8.2 Implement `reporting.queries.account_balance_snapshot()` returning per-account balances grouped by currency
- [x] 8.3 Implement `reporting.queries.monthly_summary(year, month)` returning one summary block per currency present that month
- [x] 8.4 Register the report queries as operations
- [x] 8.5 Unit-test every scenario in `reporting/spec.md` (empty month, mixed flows, savings-rate-null on zero income, drafts excluded, multi-currency)

## 9. REST API surface

- [x] 9.1 Implement `api.app.create_app(settings)` → FastAPI; mount `GET /health` (unauthenticated)
- [x] 9.2 Implement `api.auth.require_api_key` dependency reading `Authorization: Bearer …`, comparing against `settings.api.key` with a constant-time check
- [x] 9.3 Implement `api.routing.register_operations(app, registry)` that walks the registry and mounts each operation as `POST /api/<op-name>` with the operation's input model as the request body and output model as the response
- [x] 9.4 Map common errors to HTTP statuses: validation→400, auth→401, not-found→404, conflict (duplicate)→409, unexpected→500; ensure the API key is never echoed in error bodies
- [x] 9.5 Configure structured logging with key redaction; verify no log line contains the API key value
- [x] 9.6 Integration tests covering every scenario in `api-surface/spec.md` for REST (401 on missing/wrong key, 200 on /health, 400 on bad type, 409 on duplicate)

## 10. MCP server surface

- [x] 10.1 Implement `mcp.server.build_server(registry, settings)` using the official MCP Python SDK; transport: HTTP for parity with REST
- [x] 10.2 For each registered operation, register an MCP tool whose JSON Schema is derived from the input model and whose return is the output model serialized to JSON
- [x] 10.3 Apply API-key auth on the MCP transport; failed auth blocks tool listing and tool calls
- [x] 10.4 Run the MCP server in-process with FastAPI under `finance serve` (mounted at e.g. `/mcp`); document this is the single-process v1 default
- [x] 10.5 Integration tests for `mcp-server` scenarios in `api-surface/spec.md` (tool listing matches registry, tool call invokes the same callable, auth required)

## 11. Operation contract test (REST ↔ MCP)

- [x] 11.1 Implement `tests/contract/test_registry_consistency.py` that, for every operation, builds the REST OpenAPI schema and the MCP tool schema and asserts equality of input/output JSON Schemas
- [x] 11.2 Test fails when an operation is registered but missing on either surface
- [x] 11.3 Test fails when a hand-overridden schema diverges from the model on either surface

## 12. CLI

- [x] 12.1 Build the Typer app `cli.app` with subcommand groups: `account`, `transaction`, `import`, `draft`, `report`, `serve`, `bot`, `init`, `config`
- [x] 12.2 Implement `init` (calls `core.db.init_db`), `config get/set` (with `0600` perms and secret redaction)
- [x] 12.3 Implement `account create/list/archive`, `transaction add/list` — each calling registered operations
- [x] 12.4 Implement `import <adapter-id> <path> --account <name>` calling `import_artifact`; print batch id and draft count
- [x] 12.5 Implement `draft list/confirm/reject` and `report monthly <YYYY-MM> [--json]`
- [x] 12.6 Implement `serve [--with-ui]` (uvicorn run of FastAPI app, optionally mounting `web/dist` at `/`) and `bot` (Telegram poller)
- [x] 12.7 Integration tests for every scenario in `cli/spec.md` using Typer's `CliRunner`

## 13. Telegram bot

- [x] 13.1 Implement `bots.telegram.app.build_application(settings)`: load token, ensure `~/.finance/inbox/` exists at mode `0700`, set up handlers
- [x] 13.2 Implement allow-list middleware (fail-closed): refuse to start with empty `allow_list`; drop messages from non-allow-listed chats with one audit log line each
- [x] 13.3 Implement document handler: PDF received → save bytes to `~/.finance/inbox/<sha256>.pdf` (idempotent on identical re-uploads via content addressing) → reply with two inline keyboards (adapters, accounts) → on selections, call `import_artifact(adapter_id, path, account_id)` and reply with batch id + draft count
- [x] 13.4 Implement non-PDF document handler: polite decline message
- [x] 13.5 Implement `/help`, `/start` (alias for `/help`), `/balance`, `/summary [YYYY-MM]`, `/drafts` calling registered operations
- [x] 13.6 Verify token redaction in logs; add a unit test that scans log output during a handler run for the raw token
- [x] 13.7 Integration tests covering every scenario in `telegram-bot/spec.md` using a fake Telegram update fixture

## 14. Web UI

- [x] 14.1 Scaffold `src/finance/web/` with `npm create vite@latest -- --template react-ts`
- [x] 14.2 Configure Vite dev proxy `/api → http://127.0.0.1:8000`
- [x] 14.3 Implement an `apiClient` that reads the API key from `localStorage`, sends `Authorization: Bearer …`, and on 401 clears the key and re-prompts
- [x] 14.4 Implement key-entry screen shown when no key is stored (no API requests fire until a key is present)
- [x] 14.5 Implement Accounts view (list + New Account form) calling registered operations
- [x] 14.6 Implement Transactions view with filters (account / month) and an empty state
- [x] 14.7 Implement Drafts view (grouped by batch, Confirm / Reject, "Confirm all in this batch")
- [x] 14.8 Implement Summary view (monthly summary as a table; one block per currency on multi-currency months)
- [x] 14.9 Add a responsive layout (≤ 480px → cards instead of tables, collapsing nav, ≥ 44px tap targets)
- [x] 14.10 Add a CI/check script `npm run build` that produces `dist/`; wire `finance serve --with-ui` to mount it

## 15. End-to-end happy path

- [x] 15.1 E2E test: `init` → create "Wise GBP" account → `import wise-pdf tests/fixtures/wise/clean.pdf --account "Wise GBP"` → `draft list` shows N pending → confirm all → `report monthly` shows expected income/expense/savings
- [x] 15.2 E2E test (Telegram): simulate an allow-listed chat sending a PDF → adapter+account selection → confirmation → `/summary` returns the expected one-message recap
- [x] 15.3 E2E test (REST + MCP): same flow exercised via REST and via an MCP client to prove parity
- [x] 15.4 Manual checklist in README: install, init, configure, run serve, run bot, open the web UI, import a PDF, confirm drafts, view monthly summary

## 16. Documentation & polish

- [x] 16.1 README: setup with `uv`, configuration (paths, secrets, allow-list), running each surface, importing a Wise PDF, the v1 limitations and the documented backlog
- [x] 16.2 `docs/architecture.md`: short tour of the package layout, the operation registry pattern, and the ingestion pipeline (with a diagram-as-text)
- [x] 16.3 `docs/extending.md`: how to add a new institution adapter or a new operation
- [x] 16.4 Confirm `openspec validate bootstrap-finance-app --strict` passes
- [x] 16.5 Open the change for archival once all of the above is green
