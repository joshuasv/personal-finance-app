## Context

Greenfield repository, single user, local-first. The user wants one system that owns the full personal-finance loop and is callable from a CLI, a REST API, an MCP server, a Telegram bot, and a web UI — with ML-heavy ingestion (PDF, voice, text), categorization, and more bank integrations explicitly on the roadmap. v1 has to prove the loop "Wise PDF in → reviewed transactions → monthly savings out" without locking out the future expansion.

Current state: empty repo with only `openspec/` scaffolding. No language, framework, or schema chosen yet.

Constraints:
- Single user; no multi-tenant isolation needed.
- Runs on the user's own machine; SQLite is sufficient for the foreseeable horizon.
- Multiple surfaces (CLI, REST, MCP, Telegram, web) must behave identically — no surface can be the source of truth.
- ML/DL features are explicitly future work but the architecture must absorb them additively.

## Goals / Non-Goals

**Goals:**
- One Python package (`finance.core`) owns all business logic and data access. Every surface is a thin adapter on top.
- A pluggable `InstitutionAdapter` interface so adding Chase/Santander/Plaid later is "implement the interface, register it" — no core changes.
- A pluggable `IngestionSource` interface so adding voice / text / API ingestion later is similarly additive.
- A "draft transaction → review → commit" pipeline so ingestion never silently mutates the canonical ledger; this is the seam where ML categorization will plug in.
- One operation registry shared between REST and MCP so the two surfaces cannot drift.
- Schema versioned via Alembic from day one — no "we'll add migrations later."

**Non-Goals:**
- Multi-user, multi-tenant, or hosted-SaaS concerns (auth model is a single API key + a single allow-listed Telegram chat).
- Real-time bank sync, push notifications, or background scheduled jobs in v1 (manual upload is the v1 trigger).
- ML/DL features themselves — only the seams that will receive them later.
- Mobile native apps; the web UI must be responsive but no React Native / iOS / Android in v1.
- High-availability or horizontal scaling.

## Decisions

### Decision: Python end-to-end (FastAPI + Typer + React UI)
- **What**: Python 3.12, FastAPI for REST, Typer for CLI, SQLAlchemy 2.x + Alembic for persistence, `python-telegram-bot` for the bot, the official MCP Python SDK for the MCP server, React + Vite (TypeScript) for the web UI.
- **Why**: ML/DL is explicitly on the roadmap (PDF parsing, Whisper, transformers for categorization). Keeping the core in Python means future ML work is `import torch` away rather than crossing an HTTP boundary. FastAPI + Typer + the MCP SDK all consume the same Python functions, so a single operation can be exposed across three surfaces with no glue.
- **Alternatives considered**:
  - *TypeScript core + Python ML workers*: cleaner web ergonomics but every ML feature would need a service boundary, queue, and serialization story from day one — large fixed cost paid before the first ML feature ships.
  - *Go core*: most portable single-binary deploy, but pushes ML to a separate Python tier and adds a third language (TS for web). Three languages for a one-developer project is too much.

### Decision: Hexagonal layout — `core` is the only place with business logic
- **What**: Package layout under `src/finance/`:
  - `core/` — domain models, services, repositories, the operation registry. No FastAPI, no Typer, no Telegram imports.
  - `ingestion/` — `IngestionSource` and `InstitutionAdapter` protocols, the Wise PDF adapter, the draft-review pipeline.
  - `reporting/` — query primitives + monthly summary builder.
  - `api/` — FastAPI app, routers, dependency wiring, API-key auth.
  - `mcp/` — MCP server that registers tools by walking the same operation registry the API uses.
  - `cli/` — Typer app.
  - `bots/telegram/` — Telegram handlers.
  - `web/` — React + Vite app (separate `package.json`); built artifacts optionally served by FastAPI in prod.
- **Why**: Surfaces drift when each contains its own logic. Forcing every surface to call `core` (and forcing REST + MCP to share an operation registry) makes drift structurally impossible. Also keeps `core` testable without spinning up HTTP/CLI/bot machinery.
- **Alternatives considered**: Letting each surface own its own validation / orchestration. Rejected — guaranteed drift between REST and MCP (and CLI vs Telegram), which defeats the "one system" goal.

### Decision: SQLite + SQLAlchemy 2.x + Alembic, money as integer minor units
- **What**: Single SQLite database at `~/.finance/finance.db` (path configurable). Money stored as `BIGINT` minor units (cents) plus a 3-letter ISO currency code; never `float`. Schema migrations via Alembic from the first commit.
- **Why**: SQLite handles single-user volumes for years and keeps deploy to "copy a file." SQLAlchemy 2.x's typed API plays nicely with mypy. Integer-minor-units is the only safe representation for money — `float` rounding would corrupt every report. Alembic from day one prevents the "manually evolve schema in production" trap.
- **Alternatives considered**: Postgres (overkill for single user); decimal type (works, but mixing currencies on summary rows is more annoying than int math).

### Decision: One operation registry, two transports (REST + MCP)
- **What**: Each core operation (`list_transactions`, `categorize_transaction`, `summary_for_month`, etc.) is a Python callable with a Pydantic input model and a Pydantic output model, registered in `core.operations`. `api/` mounts each as a FastAPI route; `mcp/` registers each as an MCP tool. The CLI and Telegram bot also call these registered callables directly.
- **Why**: Guarantees REST and MCP can't drift. Adding a new operation appears on both surfaces automatically. Pydantic models double as the JSON Schema MCP needs and as FastAPI's request/response models.
- **Alternatives considered**: Hand-writing REST and MCP layers separately. Rejected — drift is inevitable and the user explicitly wants LLMs and humans to drive the same surface.

### Decision: Ingestion produces *draft* transactions; nothing hits the ledger without confirmation
- **What**: `IngestionSource.ingest()` returns a `DraftBatch` written to a `draft_transactions` table with status `pending`. The user reviews drafts via CLI / web / Telegram and explicitly commits them — at which point they become real `transactions` rows.
- **Why**: PDF parsing (and future ML extraction) will produce wrong rows. A review queue is the only honest design — and it's the seam where future categorization will plug in without changing core. Also gives the ledger a strong invariant: "every row was either entered manually or explicitly confirmed."
- **Alternatives considered**: Direct write with after-the-fact correction. Rejected — silent corruption, hard to audit, and provides no place for future suggest-without-committing flows.

### Decision: Defer categorization out of v1
- **What**: v1 ships no `Category` model, no rules, no `Categorizer` interface. Transactions and drafts carry only amount/date/payee/memo. Categorization (rules and/or ML) is a follow-on change that will introduce both the model and the suggestion seam, plugged in at the draft-review pipeline that already exists.
- **Why**: The user's primary v1 goal is "PDF in → savings out." Categorization is a distinct surface that needs its own design (taxonomy, rule semantics, suggestion UX, eventual ML labeling). Bundling it into v1 doubles the spec surface for a feature that produces no income/expense/savings number on its own. The draft-review pipeline already gives a clean seam to add it later without disrupting core.
- **Alternatives considered**: Ship rules in v1 (large extra surface area for a feature that doesn't move the savings number); ship categories-only in v1 with no rules (UI-only feature with no auto behavior — pure busywork at v1 ingestion volume).

### Decision: Wise PDF adapter as the v1 institution adapter, via `pdfplumber`
- **What**: `WiseStatementAdapter` implements `InstitutionAdapter`. It reads a PDF with `pdfplumber`, extracts the table region, and yields `DraftTransaction` records. Adapter selection is by user choice at upload time (no auto-detection in v1).
- **Why**: Wise is the user's only bank for v1. `pdfplumber` is mature for table-bearing PDFs and avoids ML for the v1 happy path. User-chosen adapter avoids the ambiguity of fingerprinting layouts before we have multiple to compare.
- **Alternatives considered**: OCR + layout model now (premature; Wise PDFs have machine-readable text); auto-detect adapter (premature with N=1).

### Decision: Telegram as the v1 chat surface — deterministic dispatch only
- **What**: One Telegram bot, polling mode (no webhook needed for local-first). Allow-listed by chat ID in config. The bot is a thin **deterministic dispatcher**: bare slash commands (`/help`, `/start`, `/summary`, `/balance`, `/drafts`) map 1:1 to operations in the registry, and PDF documents are saved to the inbox and handed to the ingestion pipeline. The bot does NOT call an LLM in v1; every action goes through `core.operations`. `/start` is a Telegram client convention and is treated as an alias for `/help`.
- **Why**: User has Telegram; long-polling needs no inbound port; `python-telegram-bot` is mature. The 1:1 DM context means namespaced commands (e.g., `/personal-finance:summary`) buy nothing — and Telegram's command parser does not accept `:` or `-` in command names anyway. Keeping v1 deterministic means the bot is testable end-to-end without an LLM in the loop, and an LLM bridge can be added later without rewriting auth or transport.
- **LLM bridge (backlog, not v1)**: A future change can route free-form Telegram text through a personal AI assistant (e.g., Hermes, OpenClaw) that drives the same `core.operations` via MCP. The seam is intentional: the bot already persists PDFs to durable storage and dispatches commands through the registry; an LLM bridge would consume those plus a per-chat conversation store. Per-chat conversation memory is explicitly **not** implemented in v1.
- **Alternatives considered**: WhatsApp Cloud API (paid, account approval friction); iMessage via a Mac bridge (requires always-on Mac); SMS (no PDF support); an LLM router in v1 (rejected — adds an unbounded failure mode and a model-cost line item before the deterministic path is even proven).
- **Previously**: This decision was scoped narrower (just "polling + allow-list + slash commands"); rewritten during Phase 2 to make the deterministic boundary explicit and to call out the LLM bridge as a v2 hook.

### Decision: PDF artifact handoff is path-based via `~/.finance/inbox/`
- **What**: Inbound PDFs (Telegram now; future web upload, future API upload) are written to `~/.finance/inbox/<sha256>.pdf` first; the ingestion operation receives a **filesystem path**, not bytes. The directory is created with mode `0700` on first use (matching `~/.finance/`). Files are kept indefinitely; the user prunes manually.
- **Why**: A single `import_artifact(adapter_id, path, account_id)` operation can then be driven by any surface (CLI, bot, web, future watcher) without each one inventing its own transport. It also pre-positions the project for a future external OCR worker (a separate process or container that batch-processes inbox files) without touching the bot. Content-addressed names give us free de-duplication of identical re-uploads.
- **Lifecycle**: Append-only in v1. No GC, no TTL, no auto-archive. Documented as user responsibility. A retention policy is backlog.
- **Alternatives considered**: Pass bytes through the operation signature (forces every surface to reinvent streaming and makes the operation memory-bound on large PDFs); store PDFs in SQLite as blobs (bloats the DB and breaks the "schema is structured data, files are files" separation).

### Decision: Web UI as a separate Vite app, served standalone in dev, optionally bundled in prod
- **What**: `src/finance/web/` is a Vite + React + TypeScript project with its own `package.json`. In dev it runs on `:5173` and proxies `/api/*` to FastAPI on `:8000`. In prod (`uv run finance serve --with-ui`) FastAPI mounts the built `dist/` at `/`.
- **Why**: Standard, well-trodden split that lets web evolve with hot-reload without coupling to the Python process. Single-binary deploy stays possible via the bundled mode.
- **Alternatives considered**: Server-rendered HTMX (faster to ship, but the user named "browser UI" alongside CLI/API/MCP — React is the more familiar interactive substrate and matches the "review queue" UX better).

### Decision: Two independent auth boundaries — chat-ID allow-list + API key
- **What**: There are two trust edges and they are completely independent:
  1. **Telegram bot edge**: a fixed list of allowed Telegram chat IDs (`telegram.allow_list`). The bot refuses to start if the list is empty (fail-closed). Updates from non-allow-listed chats are silently dropped with one audit log line per rejected chat ID.
  2. **REST/MCP edge**: a single API key (`api.key`) sent as `Authorization: Bearer <key>` and compared in constant time. MCP uses the same key on the same transport.

  The bot does NOT proxy through the API key — it's in the same process and calls operation callables directly via `core.operations`. So compromising the chat-ID allow-list does not grant API/MCP access, and leaking the API key does not let the attacker drive Telegram. The two edges fail independently.
- **Why**: Single-user app. One token per surface, both stored in `~/.finance/config.toml` with `0600` perms. No user table, no sessions, no OAuth dance. Independence keeps the failure model simple: each surface has exactly one secret to rotate.
- **Alternatives considered**: One unified secret across surfaces (simpler config, but a single leak compromises everything); OAuth (overkill); no auth on REST (the REST API is meant to be reachable remotely by LLMs — must have at least a key).
- **Previously**: This was originally one combined decision ("single API key for REST/MCP; chat-ID allow-list for Telegram"); rewritten during Phase 2 to make the *independence* of the two edges explicit and to lock in fail-closed semantics for the allow-list.

### Decision: No `account.type` enum in v1 — deferred to a future `is_liability` bit
- **What**: The Account model has no `type` field. Accounts are identified by `name` and partitioned only by `currency`. There is no `checking | savings | credit | cash` enum.
- **Why**: In v1 there is no code path that branches on account type — no UI grouping, no balance-sign rules, no report partitioning. The only genuine future-coupling is net-worth aggregation (knowing which balances subtract because the account is a liability), and that is a single boolean `is_liability`, not a four-value taxonomy. Shipping the enum now would freeze a vocabulary we'd have to migrate or extend (loan? brokerage? mortgage?) the moment a real requirement arrived.
- **When this changes**: When net-worth aggregation lands, a focused change introduces `account.is_liability: bool` (default `false`) with a backfill migration. Type-as-vocabulary, if ever needed for reporting, becomes a separate optional `tag`/`label` field, not a hardcoded enum.
- **Alternatives considered**: Keep the four-value enum (carries dead code through six more phases for no behavioral benefit); ship `is_liability` now (premature — there's no consumer for it in v1); leave `type` as a free-text string (worst of both — no validation, no semantics).
- **Previously**: The original spec carried a `type` enum on the Account model; dropped during Phase 2 once it was clear no v1 code branches on it.

## Risks / Trade-offs

- **PDF layouts drift** → Wise occasionally restyles statements and the parser breaks. Mitigation: the adapter has its own test suite with checked-in fixture PDFs covering each known layout version; a parser failure raises a clear error and surfaces drafts to a manual entry path rather than silently dropping rows.
- **Three surfaces sharing a registry can still drift in subtle ways** (e.g., MCP's JSON-Schema flavor vs FastAPI's) → Add a contract test that, for every registered operation, asserts both surfaces expose it with matching input/output schemas.
- **SQLite + heavy concurrent writes** (e.g., bot + web at once) → unlikely at single-user scale, but enable WAL mode and keep transactions short. Document a Postgres-migration path in design but don't implement it.
- **No categorization in v1 means reports lack a "where did the money go?" breakdown** → accepted: v1 reports income, expense, net savings, and savings rate per currency. The breakdown question is the headline feature of the future categorization change.
- **Telegram allow-list misconfig leaks data to a stranger** → bot refuses to start if no allow-list is configured (fail-closed) and logs every rejected chat ID.
- **Storing API key + Telegram bot token in a config file** → they live under `~/.finance/config.toml` with `0600` perms; documented as user responsibility. Acceptable for a local-first single-user tool.
- **`pydantic` model duplication between core and surfaces** → enforced by convention: input/output models live in `core.operations`; surfaces import them. No re-defining shapes in `api/` or `mcp/`.
- **One-developer scope creep** → the proposal explicitly lists the backlog (more banks, ML, voice/text, investments) so the boundary is visible. v1 ships only what's in v1 scope; backlog items get their own change proposals.

## Migration Plan

Greenfield — no migration. Initial deploy:
1. `uv sync` to install dependencies.
2. `uv run finance init` to create `~/.finance/finance.db` and run all Alembic migrations to head.
3. `uv run finance config set api.key <key>` and `… telegram.token <token>` and `… telegram.allow_list <chat_id>`.
4. `uv run finance serve` starts REST + MCP. `uv run finance bot` starts the Telegram poller. `npm --prefix src/finance/web run dev` for the web UI in dev.

Rollback: stop the processes, restore the SQLite file from a backup. Document a "back up `~/.finance/` before any schema migration" guidance in the README.

## Open Questions

- Should the MCP server run in-process with FastAPI (one `uv run finance serve` process) or as a separate command? Leaning in-process for v1 (simpler), separable later if it grows.
- What's the canonical "month boundary" for the savings report — calendar month, or a user-configurable cycle (e.g., paydate-to-paydate)? v1 will ship calendar-month and treat configurable cycles as a follow-on.
