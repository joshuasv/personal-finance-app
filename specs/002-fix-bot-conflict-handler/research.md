# Research: Fix Telegram Bot Conflict Error Handler

## PTB Error Handler API (v22.7)

**Decision**: Use `Application.add_error_handler(callback)` with an async callback `(update: object, context: ContextTypes.DEFAULT_TYPE) -> None`. `context.error` carries the exception.

**Rationale**: This is the standard PTB mechanism — already used by the library's own network loop to surface errors. It requires no changes to the polling loop or CLI entry point.

**Signature confirmed**:
```
Application.add_error_handler(callback, block=True) -> None
```
`block=True` (default) means the loop waits for the error handler coroutine to return before processing the next update — safe for our use case.

---

## Stopping the Application from Inside an Error Handler

**Decision**: Schedule the stop as a new asyncio task rather than awaiting it directly.

```python
asyncio.get_running_loop().create_task(context.application.stop())
```

**Rationale**: `await context.application.stop()` from inside an error handler can deadlock in PTB v20+ because `stop()` may join internal tasks that are currently blocked waiting for the error handler to return. Scheduling it as a task lets the event loop run the stop *after* the current error handler frame returns, avoiding the deadlock. This pattern is consistent with PTB's own recommended "stop from handler" examples.

**Alternative considered**: `raise SystemExit(1)` — rejected because it terminates the process immediately without letting PTB clean up connections, leaving Telegram's long-poll in an indeterminate state. `context.application.stop()` issues a clean shutdown that lets `run_polling()` exit normally.

**Exit code**: After `stop()` is called, `run_polling()` returns and the process exits. The CLI entry point does not currently call `sys.exit()` explicitly; Python exits with code 0 by default after `main()` returns. To guarantee a non-zero exit code, the error handler should set a flag checked after `run_polling()` returns, or call `sys.exit(1)` as part of the stop sequence.

**Practical approach**: Simplest correct implementation — set a module-level flag in the error handler; after `run_polling()` returns in the CLI, check the flag and call `sys.exit(1)`. Alternatively, re-raise `SystemExit(1)` inside `application.post_stop`. For this fix the simplest approach is acceptable: the critical log + shutdown is the observable behaviour; exit code is a nice-to-have.

---

## Stale Process Detection in `dev.sh`

**Decision**: Use `pgrep -f "finance bot"` to find stale processes, filtering out the current shell's own PID.

**Rationale**: `pgrep -f` matches against the full command string, so it finds `uv run finance bot` processes without false-positives from other commands. Available on Linux (procps) and macOS (BSD pgrep).

**Implementation sketch**:
```bash
if command -v pgrep &>/dev/null; then
  stale=$(pgrep -f "finance bot" | grep -v "^$$\$")
  if [[ -n "$stale" ]]; then
    echo "[dev] killing stale bot process $stale"
    kill "$stale" 2>/dev/null || echo "[dev] warning: could not kill $stale"
    sleep 0.5  # give Telegram time to release the long-poll
  fi
fi
```

**Graceful degradation**: `command -v pgrep` guard prevents failure on environments without pgrep. `kill ... || true` prevents abort if the process already exited between detection and kill.

**Alternative considered**: PID file written by the bot on startup — rejected as it requires changes to bot startup code and is fragile (stale PID files after crashes). `pgrep` is stateless and always accurate.

---

## Test Strategy

**Decision**: Unit test in `tests/integration/test_telegram_bot.py` (existing bot test module) using `unittest.mock.AsyncMock`.

**Why integration test module**: Existing bot tests already mock `Application`, `Update`, and `Context`. The new test follows the same pattern: build a mock context with `context.error = Conflict(...)` and `context.application.stop = AsyncMock()`, call the error handler directly, and assert on the mock.

**Test cases needed**:
1. Conflict exception → `context.application.stop` called once, CRITICAL logged
2. Non-Conflict exception → `context.application.stop` not called, ERROR logged

**Import path**: The error handler function must be importable. Expose it as `_on_error` (or similar) from `finance.bots.telegram.app` — private by convention but reachable in tests.
