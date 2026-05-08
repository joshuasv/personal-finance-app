## ADDED Requirements

### Requirement: Handlers are reachable through the Application dispatcher
Every registered handler — slash commands (`/help`, `/start`, `/summary`, `/balance`, `/drafts`), the document handler, and the callback handler — SHALL be invokable end-to-end by dispatching a `python-telegram-bot` `Update` object through `Application.process_update(update)` against an `Application` built by `build_application(...)`. A test that submits a properly-shaped `Update` SHALL observe the bot send the documented reply on the bot's outgoing-message surface.

This requirement is the regression net that catches handler-registration bugs, filter-mismatches, dispatcher-routing bugs, and allow-list payload-shape mismatches that handler-only tests cannot see.

#### Scenario: /help is reachable through the dispatcher
- **GIVEN** an `Application` built from a valid `Settings` with allow-list `[12345]`
- **AND** the `Application.bot` replaced with a stub that records outgoing messages
- **WHEN** an `Update` representing chat `12345` sending `/help` is dispatched via `Application.process_update`
- **THEN** the stub bot records exactly one `send_message` call whose text begins with the documented "Commands:" preamble

#### Scenario: PDF upload is reachable through the dispatcher
- **GIVEN** an `Application` built as above
- **AND** at least one active account exists in the database
- **WHEN** an `Update` representing chat `12345` sending a document with `mime_type="application/pdf"` is dispatched via `Application.process_update`
- **THEN** the stub bot records a `send_message` call whose text contains "PDF saved" and whose `reply_markup` is an inline keyboard listing the available adapters

#### Scenario: PDF with octet-stream mime is still handled
- **GIVEN** an `Application` built as above
- **AND** at least one active account exists
- **WHEN** an `Update` is dispatched with a document whose `mime_type` is `application/octet-stream` but whose `file_name` ends in `.pdf`
- **THEN** the stub bot records the same "PDF saved" reply as the canonical-mime case (Telegram occasionally emits `octet-stream` for PDFs; the bot must accept both)

#### Scenario: Disallowed chat is silently dropped at the dispatcher and audited
- **GIVEN** an `Application` built with allow-list `[12345]`
- **WHEN** an `Update` representing chat `99999` sending `/help` is dispatched
- **THEN** the stub bot records zero outgoing messages
- **AND** exactly one log line at WARNING (or higher) is emitted containing the rejected chat id `99999`

## MODIFIED Requirements

### Requirement: Telegram bot process
The system SHALL provide a Telegram bot, started via `finance bot`, that connects to Telegram using long polling with a bot token loaded from configuration. The bot SHALL share the same `core.operations` registry as the API and CLI; it MUST NOT contain business logic of its own. **Logging SHALL be configured by the CLI startup path (the same redacting filter used by `finance serve`) before `Application.run_polling(...)` is invoked**, so that handler-registration messages, allow-list audit lines, and any errors raised inside handlers are visible in the operator's terminal.

#### Scenario: Bot starts and registers handlers
- **GIVEN** a valid `telegram.token` and a non-empty `telegram.allow_list`
- **WHEN** the user runs `finance bot`
- **THEN** the process connects to Telegram, registers the documented handlers, and emits at least one INFO-level log line confirming startup before entering the polling loop

#### Scenario: Bot startup logs are not silent
- **GIVEN** a valid configuration as above
- **WHEN** the user runs `finance bot`
- **THEN** the launching terminal SHALL receive at least one log line within the first two seconds of startup (proving the logging stack is wired before polling begins)
