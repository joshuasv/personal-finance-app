# telegram-bot

## Purpose

Telegram chat ingress that accepts PDF statement uploads (persisted to `~/.finance/inbox/<sha256>.pdf` before ingestion), runs ingestion through `core.operations`, and answers bare slash commands. Deterministic dispatch only in v1; no LLM bridge.

## Requirements

### Requirement: Telegram bot process
The system SHALL provide a Telegram bot, started via `finance bot`, that connects to Telegram using long polling with a bot token loaded from configuration. The bot SHALL share the same `core.operations` registry as the API and CLI; it MUST NOT contain business logic of its own.

#### Scenario: Bot starts and registers handlers
- **GIVEN** a valid `telegram.token` and a non-empty `telegram.allow_list`
- **WHEN** the user runs `finance bot`
- **THEN** the process connects to Telegram, registers the documented handlers, and logs "bot ready"

### Requirement: Chat allow-list (fail-closed)
The bot SHALL load a list of allowed Telegram chat IDs from `telegram.allow_list` in configuration. Updates from chat IDs not in the list SHALL be silently ignored except for a single audit log line per rejected chat ID. If the allow-list is empty or unset, the bot SHALL refuse to start.

#### Scenario: Refuse to start with empty allow-list
- **WHEN** `telegram.allow_list` is empty and the user runs `finance bot`
- **THEN** the process exits non-zero with a message instructing the user to configure the allow-list

#### Scenario: Drop a message from a non-allow-listed chat
- **GIVEN** a configured allow-list of `[12345]`
- **WHEN** chat `99999` sends a message
- **THEN** no reply is sent, no operation runs, and one audit log line is written naming chat `99999`

### Requirement: Accept PDF statement uploads (saved to inbox first, path-based handoff)
The bot SHALL accept PDF documents from allow-listed chats. On receipt, the bot SHALL persist the PDF bytes to `~/.finance/inbox/<sha256>.pdf` (creating the directory at mode `0700` if absent) BEFORE any further processing. Subsequent ingestion calls SHALL reference the file by filesystem path, not by in-memory bytes — the operation signature is `import_artifact(adapter_id, path, account_id)`. The bot SHALL then prompt the user via inline keyboards to pick an institution adapter and target account; once both are selected, the bot SHALL invoke the registered `import_artifact` operation and reply with the resulting draft count and a hint on how to review. Inbox files are kept indefinitely in v1; the system SHALL NOT auto-delete or auto-archive them.

#### Scenario: PDF is saved to inbox before adapter selection
- **WHEN** an allow-listed chat sends a PDF
- **THEN** the bytes are first written to `~/.finance/inbox/<sha256>.pdf` (creating the directory at mode `0700` if absent), and only then does the bot reply with the adapter/account keyboards

#### Scenario: PDF triggers adapter and account picker
- **WHEN** an allow-listed chat sends a PDF (already persisted to the inbox)
- **THEN** the bot replies with two inline keyboards: one listing registered institution adapters, the other listing non-archived accounts

#### Scenario: Successful import reply
- **WHEN** the user picks `wise-pdf` and account "Wise GBP" and the import succeeds with N drafts
- **THEN** the bot replies with a message containing the batch id and `"Created N drafts. Use /drafts to review."`

#### Scenario: Identical re-uploads collapse to one inbox file
- **WHEN** the same PDF is sent twice from any allow-listed chat
- **THEN** both messages target the same `~/.finance/inbox/<sha256>.pdf` path (content-addressed); the second write is idempotent and does not duplicate the file on disk

#### Scenario: Failed import reply
- **WHEN** the import fails (e.g., parser error, currency mismatch)
- **THEN** the bot replies with a one-message error containing the adapter id and a brief reason; no drafts are written

#### Scenario: Non-PDF documents are politely declined
- **WHEN** an allow-listed chat sends a non-PDF document (e.g., `.csv`, `.png`)
- **THEN** the bot replies that v1 only accepts PDF and points to other surfaces for other formats

### Requirement: Slash commands
The bot SHALL implement these bare (un-namespaced) slash commands for allow-listed chats:
- `/help` — list available commands.
- `/start` — Telegram client convention sent on first contact; treated as an alias for `/help`.
- `/balance` — print the per-account balance snapshot.
- `/summary [YYYY-MM]` — print the monthly summary (defaults to the current month if no argument).
- `/drafts` — print up to the 10 oldest pending drafts with their ids and a hint to confirm/reject via the web UI or CLI.

Command names use the bare form (e.g., `/summary`, not `/personal-finance:summary`) because the bot operates in 1:1 DMs with allow-listed users; namespacing buys no disambiguation, and Telegram's command parser does not accept `:` or `-` in command names.

#### Scenario: /start replies with help
- **WHEN** an allow-listed user sends `/start`
- **THEN** the bot replies with the same content as `/help`

#### Scenario: /summary with no argument
- **WHEN** an allow-listed user sends `/summary` on 2026-05-15
- **THEN** the bot replies with the monthly summary for 2026-05 as a single message containing income, expense, net savings, and savings rate

#### Scenario: /summary with explicit month
- **WHEN** an allow-listed user sends `/summary 2026-04`
- **THEN** the bot replies with the monthly summary for 2026-04

#### Scenario: /balance lists per-account balances
- **WHEN** an allow-listed user sends `/balance`
- **THEN** the bot replies with one line per non-archived account showing the formatted balance and currency

#### Scenario: /drafts shows pending drafts
- **WHEN** an allow-listed user sends `/drafts` and there are pending drafts
- **THEN** the bot replies with up to 10 oldest pending drafts (id, date, payee, amount) and a footer instructing how to act on them

#### Scenario: /drafts with no pending drafts
- **WHEN** an allow-listed user sends `/drafts` and there are no pending drafts
- **THEN** the bot replies "No pending drafts."

### Requirement: Bot uses operation registry, not direct DB access (deterministic dispatch only in v1)
Every bot action that reads or mutates data SHALL invoke a callable from the `core.operations` registry; the bot module MUST NOT import the database session or models directly. v1 is a deterministic dispatcher only — the bot SHALL NOT call any LLM, model API, or non-registry side effect when handling an update. (A future LLM bridge that hands free-form text to a personal AI assistant via MCP is explicitly out of scope for v1; see proposal backlog.)

#### Scenario: New operation surfaces nothing in the bot until wired
- **GIVEN** a new core operation `archive_account` added to the registry
- **WHEN** the bot starts
- **THEN** the operation is reachable only via REST/MCP/CLI; the bot does not silently expose it (handlers must be added explicitly)

### Requirement: Token and chat-ID handling
The bot SHALL never log the raw `telegram.token`. Chat IDs MAY appear in logs for audit (rejected-chat events explicitly include them).

#### Scenario: Token does not appear in logs
- **WHEN** the bot starts and runs through any handler
- **THEN** no log line contains the raw bot token value
