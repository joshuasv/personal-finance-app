# cli

## Purpose

Local Typer command surface mirroring the API operations for scripting and power use.

## Requirements

### Requirement: Typer CLI entrypoint
The system SHALL provide a `finance` command implemented with Typer. Running `finance --help` SHALL list all available subcommands grouped by area (`account`, `transaction`, `import`, `draft`, `report`, `serve`, `bot`, `init`, `config`).

#### Scenario: Help lists all subcommand groups
- **WHEN** the user runs `finance --help`
- **THEN** the output lists each subcommand group above with a one-line description

### Requirement: CLI commands call core operations directly
Every CLI command that mutates or queries data SHALL invoke a callable from the `core.operations` registry; CLI commands MUST NOT contain business logic. The CLI's role is restricted to argument parsing, input shaping, calling the operation, and rendering the output.

#### Scenario: CLI mutation goes through the registry
- **WHEN** the user runs `finance account create --name "Wise GBP" --type checking --currency GBP`
- **THEN** the CLI invokes the registered `create_account` operation with a validated input model, and any failure surfaces from the operation rather than the CLI

### Requirement: Init command
The system SHALL provide `finance init` which creates the configured database file (default `~/.finance/finance.db`), runs all Alembic migrations to head, and prints a confirmation summary.

#### Scenario: Init from scratch
- **WHEN** the user runs `finance init` against a non-existent database path
- **THEN** the database file is created, schema is at head, and the output shows the path and the applied migration revision

#### Scenario: Init is idempotent
- **WHEN** the user runs `finance init` against an already-initialized database
- **THEN** the command exits `0`, applies no migrations, leaves data unchanged, and prints "already initialized"

### Requirement: Config command
The system SHALL provide `finance config get <key>` and `finance config set <key> <value>` for managing the `~/.finance/config.toml` file. Setting `api.key`, `telegram.token`, or `telegram.allow_list` SHALL update the file with `0600` permissions. `finance config get` SHALL never print secret values to the terminal in full; secrets SHALL be redacted to a prefix and a length indicator.

#### Scenario: Set and get a non-secret value
- **WHEN** the user runs `finance config set db.path ~/.finance/test.db` then `finance config get db.path`
- **THEN** the second command prints the path verbatim

#### Scenario: Get a secret value redacts
- **GIVEN** `api.key` is set to a Stripe-style key with prefix `sk_live_` followed by an opaque body
- **WHEN** the user runs `finance config get api.key`
- **THEN** the output preserves the prefix and the first 4 body characters, then renders an ellipsis and the total length (for example, `sk_live_abcd…(20 chars)`) rather than the raw value

#### Scenario: Config file gets `0600` permissions
- **WHEN** the user runs `finance config set api.key …` and the file is created or rewritten
- **THEN** the file's mode is `0600`

### Requirement: Import command for statements
The system SHALL provide `finance import <adapter-id> <path> --account <account>` which runs the named institution adapter against the file at `path`, targeting the specified account. The command SHALL print the resulting batch id and the number of drafts created.

#### Scenario: Import a Wise PDF
- **WHEN** the user runs `finance import wise-pdf ./statement.pdf --account "Wise GBP"`
- **THEN** the Wise adapter parses the PDF, the resulting drafts are written under a new ingestion batch, and the command prints the batch id and draft count

#### Scenario: Unknown adapter id
- **WHEN** the user runs `finance import madeup-adapter ./statement.pdf --account "Wise GBP"`
- **THEN** the command exits non-zero with a message listing the available adapters

### Requirement: Draft review commands
The system SHALL provide `finance draft list` (filtered by account / status / batch), `finance draft confirm <id>`, and `finance draft reject <id>`.

#### Scenario: List pending drafts
- **WHEN** the user runs `finance draft list --status pending`
- **THEN** the output is a table with columns: id, date, account, payee, amount

#### Scenario: Confirm a draft
- **WHEN** the user runs `finance draft confirm <id>`
- **THEN** the underlying confirm operation runs and the command prints the new transaction id

### Requirement: Report command
The system SHALL provide `finance report monthly <YYYY-MM>` which prints the monthly summary (income, expense, net savings, savings rate). Output format SHALL default to a human-readable table and SHALL support `--json` for machine-readable output.

#### Scenario: Monthly summary table
- **WHEN** the user runs `finance report monthly 2026-05`
- **THEN** the output is a rendered table containing the summary fields defined by the reporting capability

#### Scenario: Monthly summary as JSON
- **WHEN** the user runs `finance report monthly 2026-05 --json`
- **THEN** the output is valid JSON matching the operation's output schema

### Requirement: Serve and bot commands
The system SHALL provide `finance serve` which starts the FastAPI app (REST + MCP) and `finance bot` which starts the Telegram poller. Both SHALL read configuration from `~/.finance/config.toml`. `finance serve --with-ui` SHALL additionally mount the built web UI at `/`.

#### Scenario: Serve starts on configured port
- **WHEN** the user runs `finance serve` with `api.host=127.0.0.1` and `api.port=8000`
- **THEN** the process listens on `127.0.0.1:8000` and `GET /health` returns `200`

#### Scenario: Bot refuses to start without an allow-list
- **WHEN** the user runs `finance bot` and `telegram.allow_list` is empty
- **THEN** the command exits non-zero with a message instructing the user to set `telegram.allow_list`
