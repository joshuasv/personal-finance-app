# Feature Specification: Fix Telegram Bot Conflict Error Handler

**Feature Branch**: `002-fix-bot-conflict-handler`

**Created**: 2026-06-06

**Status**: Draft

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Bot exits cleanly when a duplicate instance is detected (Priority: P1)

When the bot detects that another instance is already running (HTTP 409 Conflict from Telegram), it must immediately stop itself rather than continue polling. Continuing in this state splits incoming messages between two instances unpredictably, so a clean shutdown is the only safe response.

**Why this priority**: Silent continuation on a Conflict error is the root failure mode — messages are dropped or double-handled, the user sees no indication of the problem, and the only fix is manual process inspection. Failing loudly is strictly better.

**Independent Test**: Can be fully tested by invoking the error handler directly with a mock Conflict exception and asserting shutdown is triggered. Delivers reliable single-instance operation without needing real Telegram credentials.

**Acceptance Scenarios**:

1. **Given** the bot is running, **When** a Conflict error (HTTP 409) is received by the error handler, **Then** the bot emits a CRITICAL log message containing "another bot instance" and initiates application shutdown.
2. **Given** the error handler has fired on a Conflict, **When** the process exits, **Then** the exit code is non-zero.
3. **Given** a non-Conflict error (e.g. network timeout) arrives at the error handler, **When** the handler processes it, **Then** the error is logged at ERROR level and the bot continues running without shutting down.

---

### User Story 2 - Dev launcher kills stale bot process before starting a new one (Priority: P2)

When a developer runs `make run-all` while a previous bot process is still alive — e.g. because the terminal was closed without Ctrl-C — the launcher finds and terminates the stale process before spawning a new one. This prevents the Conflict condition from arising in the first place during development.

**Why this priority**: Prevents the P1 scenario from ever occurring in the normal dev workflow. Lower priority than P1 because P1 is the correct safety net even when this guard is absent.

**Independent Test**: Manually start a background bot process, then run `scripts/dev.sh`. Verify the stale process is killed and a single bot process remains.

**Acceptance Scenarios**:

1. **Given** a bot process is already running, **When** `scripts/dev.sh` starts, **Then** it kills the stale process and logs the killed PID before launching a new bot.
2. **Given** no stale bot process exists, **When** `scripts/dev.sh` starts, **Then** it proceeds normally with no kill step and no error output.
3. **Given** the stale process is killed, **When** the new bot starts, **Then** it polls successfully with no Conflict errors.

---

### Edge Cases

- What if the Conflict error fires multiple times before shutdown completes? The handler must be idempotent — repeated invocations must not panic or produce duplicate shutdown calls.
- What if `pgrep` is unavailable on the developer's machine? The stale-process guard must degrade gracefully (log a warning, skip the kill) rather than aborting `dev.sh`.
- What if the stale process belongs to a different user and `kill` is refused? The script must log the failure and continue the launch rather than aborting.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The bot MUST register an error handler at startup that receives all unhandled exceptions from the Telegram polling loop.
- **FR-002**: When the error handler receives a Conflict exception (HTTP 409), it MUST emit a CRITICAL-level log message containing the phrase "another bot instance".
- **FR-003**: When the error handler receives a Conflict exception, it MUST trigger application shutdown so the process exits with a non-zero status.
- **FR-004**: When the error handler receives any exception that is NOT a Conflict, it MUST log the exception at ERROR level and allow the bot to continue running.
- **FR-005**: The error handler MUST be idempotent — invoking it more than once with a Conflict exception must not cause duplicate shutdown calls or unhandled exceptions within the handler.
- **FR-006**: The dev launcher MUST check for a running bot process before starting its own bot child.
- **FR-007**: If a stale bot process is found, the launcher MUST terminate it and log a line containing the stale process PID before proceeding.
- **FR-008**: If no stale process is found, the launcher MUST proceed without producing extra output or error.
- **FR-009**: If terminating the stale process fails (permission denied, process already gone), the launcher MUST log the failure and continue rather than aborting the launch.

### Key Entities

- **Error handler**: An async callback registered with the bot application that is invoked for all unhandled exceptions from the polling loop. Receives application context and the originating exception.
- **Stale process**: A bot OS process that is already holding a long-poll connection to Telegram when a new instance attempts to start.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A unit test invoking the error handler with a mock Conflict exception confirms application shutdown is triggered exactly once.
- **SC-002**: A unit test invoking the error handler with a non-Conflict exception confirms shutdown is never triggered.
- **SC-003**: All existing bot tests pass without modification after the changes.
- **SC-004**: Running the dev launcher immediately after a previous uncleaned session results in a single running bot process within 5 seconds, with no Conflict errors in the log.
- **SC-005**: The CRITICAL log line for a duplicate-instance condition is visible to the developer within one polling cycle (approximately 10 seconds) of the conflict arising.

## Assumptions

- The `python-telegram-bot` library version in use supports `Application.add_error_handler` and async error handler callbacks.
- Initiating shutdown from within the error handler via the application's stop mechanism is supported and causes `run_polling()` to return cleanly.
- The bot is invoked via `uv run finance bot`, so identifying the process by that command string is reliable.
- `pgrep` is available in CI and developer environments (Ubuntu / macOS). Absence is handled gracefully.
- No changes to Telegram token configuration, allow-list, database schema, or message-handling logic are required.
- The fix is limited to process lifecycle; external behaviour (commands, document handling, callbacks) is unchanged.
