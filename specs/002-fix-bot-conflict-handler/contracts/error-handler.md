# Contract: Telegram Bot Error Handler

## Handler Registration

The error handler is registered once, inside `build_application()`, before the caller invokes `run_polling()`:

```
Application.add_error_handler(_on_error, block=True)
```

## Handler Signature

```
async _on_error(update: object, context: CallbackContext) -> None
```

`context.error` — the exception raised by the polling loop or a handler.

## Routing Table

| Exception type            | Log level | Message contains              | Shutdown triggered |
|---------------------------|-----------|-------------------------------|--------------------|
| `telegram.error.Conflict` | CRITICAL  | "another bot instance"        | Yes                |
| Any other exception       | ERROR     | repr / str of the exception   | No                 |

## Shutdown Sequence (Conflict path)

1. Log CRITICAL message.
2. Schedule `context.application.stop()` as an asyncio task (non-blocking inside the handler).
3. Return from handler.
4. Event loop runs the stop task → `run_polling()` exits.
5. CLI entry point detects `_conflict_seen` flag and calls `sys.exit(1)`.

## Idempotency

If `_on_error` is invoked more than once with a Conflict (possible if PTB retries before stop completes), the handler must not schedule `stop()` more than once. Guard with `_conflict_seen` flag — skip the stop task if it was already scheduled.

## Observability

- CRITICAL log line is emitted to the root logger (`finance.bots.telegram.app`) and therefore visible in the `[bot]` prefix stream of `scripts/dev.sh`.
- Non-Conflict errors produce an ERROR line with the full exception string; tracebacks are logged at DEBUG level only to avoid noise in normal operation.
