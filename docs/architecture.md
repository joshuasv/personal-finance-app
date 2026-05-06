# Architecture

Single-user, local-first. One Python core that owns all business logic,
five surfaces (CLI, REST, MCP, Telegram, web) that dispatch into it.

## Package layout

```
src/finance/
  core/                # domain (no FastAPI / Typer / Telegram imports here)
    config.py          # pydantic-settings → ~/.finance/config.toml + env
    paths.py           # ~/.finance resolver, mode 0700
    db.py              # engine, session_scope, init_db
    money.py           # Money(minor, currency); never floats at boundaries
    validators.py      # CurrencyCode + MinorUnits Pydantic types
    models.py          # SQLAlchemy models: Account, Transaction, IngestionBatch, DraftTransaction
    repositories/      # CRUD over the session
    services/          # invariants on top of repositories (typed errors)
    operations/        # the operation registry
      operation.py     # the Operation value type
      registry.py      # OperationRegistry (register/get/has/all)
      models.py        # Pydantic input/output models for every op
      bootstrap.py     # wires every service as a registered Operation
  ingestion/
    protocols.py       # InstitutionAdapter + ParsedTransaction
    registry.py        # AdapterRegistry
    wise_pdf.py        # the v1 adapter
    pipeline.py        # import_artifact + dedup-by-batch
    review.py          # confirm_draft / reject_draft
  reporting/
    queries.py         # monthly_summary, income_expense_for_month, balance_snapshot
  api/
    app.py             # create_app(settings) → FastAPI
    auth.py            # require_api_key dependency
    routing.py         # walks registry → POST /api/<op-name>
  mcp/
    server.py          # FastMCP that walks the same registry
  cli/
    app.py             # Typer app (finance ...)
    _runtime.py        # session/operation/IO helpers
  bots/telegram/
    app.py             # build_application(settings) → telegram.ext.Application
    auth.py            # AllowList (fail-closed)
    inbox.py           # ~/.finance/inbox/<sha256>.pdf
    handlers.py        # /help, /balance, /summary, /drafts + PDF + callback
  web/                 # Vite + React + TS — its own package.json
```

## The operation registry pattern

Every domain capability is a registered `Operation`:

```
Operation(
    name=str,
    input_model=type[BaseModel],
    output_model=type[BaseModel],
    callable=Callable[[Session, Input], Output],
    description=str,
    tags=tuple[str, ...],
)
```

Surfaces walk the registry:

```
                     +--------------------+
                     |  OperationRegistry |
                     +--------------------+
                          /     |      \
                    REST     MCP        CLI
                  /api/<op> tool/<op> finance <subcmd>
                                              ^
                                              |
                                    Telegram handlers (same callable)
```

- `api/routing.py` mounts each operation as `POST /api/<op-name>` with the
  Pydantic input model as the request body and the output model as the
  response.
- `mcp/server.py` registers each operation as an MCP tool whose JSON Schema
  is derived from the same Pydantic input model.
- `cli/app.py` calls `_runtime.run_operation(op, payload, settings)` per
  subcommand, which validates the payload and runs the callable in a single
  committed session.
- `bots/telegram/handlers.py` dispatches each slash command and the PDF
  callback flow to the same registry.

This is the structural guarantee that REST and MCP cannot drift: a contract
test in `tests/contract/test_registry_consistency.py` walks both surfaces
and asserts every operation appears with matching input/output schemas.

## The ingestion pipeline

```
+---------+  PDF   +---------------+   ParsedTransaction
| Surface |------->| InstitutionAd |---------------+
| (CLI/   |        | (e.g. wise-   |               v
| bot/etc)|        |  pdf)         |     +-----------------+
+---------+        +---------------+     |   pipeline.py   |
                                         | import_artifact |
                                         +-----------------+
                                                  |
                                  IngestionBatch  v   DraftTransaction(status=pending)
                                                  |
                                                  v
                                         +-----------------+
                                         | review.py       |
                                         | confirm_draft / |
                                         | reject_draft    |
                                         +-----------------+
                                                  |
                                                  v
                                          Transaction (canonical ledger)
```

Key invariants:
- The canonical ledger is **never written** by the parser. Drafts always come
  first. `confirm_draft` is the only path that produces a `Transaction` for
  imported data.
- Source PDFs are content-addressed at `~/.finance/inbox/<sha256>.pdf`
  before any parsing happens. The Telegram bot, the CLI, and (eventually) a
  web upload all hand a path to the same `import_artifact` operation.
- Re-uploading the same PDF is detectable: `IngestionBatch.source_sha256`
  is unique per upload; `import_artifact` refuses without `force=True`.

## Auth model — two independent edges

- **REST + MCP** share one API key (`api.key`), sent as
  `Authorization: Bearer …` and compared in constant time. The MCP transport
  is wrapped in an ASGI middleware that enforces the same key before tools
  can be listed or called.
- **Telegram** uses an allow-list of chat IDs (`telegram.allow_list`).
  Empty list = bot refuses to start (fail-closed). Non-allow-listed chats
  are silently dropped with one audit-log line each.

Compromising the chat allow-list does not grant API/MCP access; leaking the
API key does not let an attacker drive Telegram. The two edges fail
independently.

## Money

Money is **always** integer minor units plus a 3-letter ISO currency code.
Floats at API/CLI boundaries are rejected with `pydantic` validation
errors that point at the offending field. `core.money.Money` knows how
many decimals each currency uses (JPY/KRW = 0; BHD/JOD/etc = 3; everything
else = 2) and renders human-readable strings (`12.50 GBP`).
