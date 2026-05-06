## Why

I want one local-first system that owns my personal finances end-to-end: ingest bank statements and tell me — at a glance — how much I saved this month. No spreadsheet drift, no SaaS lock-in, and a surface that both I (CLI/web/chat) and an LLM (REST + MCP) can drive identically. v1 needs to prove the loop "Wise PDF in → reviewed transactions → monthly savings out," with the architecture deliberately leaving room for more banks, ML categorization (future), voice/text ingestion, and (much later) investment tracking.

## What Changes

- Stand up a Python monorepo with a single core domain package that all surfaces (CLI, REST, MCP, Telegram bot, web UI) call into — no business logic in surface layers.
- Introduce the **ledger** data model: accounts (multi-currency) and transactions. v1 ships without categories — every transaction is just an amount, payee, date, and memo. Categorization is explicitly deferred to a later change.
- Introduce a pluggable **institution-adapter** interface; ship one concrete adapter for **Wise PDF statements**. Future adapters (Chase, Santander, Plaid, SimpleFIN) implement the same interface without touching core.
- Introduce an **ingestion pipeline** with a draft-transaction review queue: parsed transactions land as drafts and the user confirms/edits before they hit the canonical ledger.
- Build a **monthly summary report** primitive: income, expense, savings rate, balance — exposed identically across all surfaces.
- Expose the core via a **REST API** (FastAPI, API-key auth, single-user) and a co-located **MCP server** wrapping the same operations as native tools for Claude.
- Ship a **Typer CLI** for local power use and scripting.
- Ship a **Telegram bot** that accepts a PDF upload (saved to `~/.finance/inbox/` first), runs the ingestion pipeline through `core.operations`, and responds to bare slash commands (`/help`, `/start`, `/summary`, `/balance`, `/drafts`). The bot is a deterministic dispatcher in v1 — no LLM in the loop.
- Ship a **read-and-confirm web UI** (React + Vite) for visual review of transactions, drafts awaiting confirmation, and the monthly summary.
- Establish project conventions: SQLite via SQLAlchemy + Alembic migrations, `uv` for env management, `ruff` + `mypy` + `pytest`, settings via `pydantic-settings`.

## Capabilities

### New Capabilities
- `ledger-core`: Canonical data model and operations for accounts and transactions. The single source of truth every other capability calls into.
- `statement-ingestion`: Institution-adapter abstraction, the Wise PDF adapter, the parsing pipeline, and the draft-transaction review queue.
- `reporting`: Monthly summary report (income, expense, savings, savings rate) and the query primitives behind it.
- `api-surface`: Single-user REST API (FastAPI) plus co-located MCP server exposing the same operations as native tools, sharing one auth model and one operation registry.
- `cli`: Local Typer command surface mirroring the API operations for scripting and power use.
- `telegram-bot`: Telegram chat ingress that accepts PDF statement uploads (persisted to `~/.finance/inbox/<sha256>.pdf` before ingestion), runs ingestion through `core.operations`, and answers bare slash commands. Deterministic dispatch only in v1; no LLM bridge.
- `web-ui`: Browser UI (React + Vite) for visual review of transactions, the draft review queue, and the monthly summary.

### Modified Capabilities
<!-- None — this is the bootstrap change; no prior specs exist. -->

## Impact

- **Code**: Greenfield repository. Establishes the package layout (`src/finance/{core,ingestion,reporting,api,mcp,cli,bots,web}`), the database schema (initial Alembic migration), and the test layout (`tests/{unit,integration}`).
- **Dependencies**: Adds FastAPI, Typer, SQLAlchemy, Alembic, pydantic-settings, pdfplumber, python-telegram-bot, the MCP Python SDK, and React/Vite for the web UI. Dev tooling: `uv`, `ruff`, `mypy`, `pytest`.
- **Runtime / deployment**: Single-user, local-first. SQLite file under `~/.finance/`. One process serves REST + MCP; the Telegram bot and web UI dev server run separately. No external services required for v1 beyond a Telegram bot token.
- **Security**: Single-user API key for REST/MCP; Telegram bot restricted by allow-listed chat ID. Statement PDFs and the SQLite database stay local; nothing is sent to third parties in v1.
- **Out of scope (explicit backlog)**: categorization (rules and/or ML); bank-aggregator integrations beyond Wise; voice/text-note ingestion; WhatsApp/iMessage bridges; investment tracking and recommendations; an LLM bridge that hands free-form Telegram messages to a personal AI assistant (e.g., Hermes, OpenClaw) to drive `core.operations` via MCP, with per-chat conversation memory; net-worth aggregation (and the `account.is_liability` bit it would introduce); an inbox retention/GC policy. The institution-adapter, ingestion-pipeline, and operation-registry abstractions exist specifically to make these additive rather than disruptive.
