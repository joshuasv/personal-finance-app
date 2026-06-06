# Data Model: Fix Telegram Bot Conflict Error Handler

No new persistent data entities are introduced by this feature.

## Runtime State

**`_conflict_seen` flag** (module-level bool in `app.py`, default `False`):
- Set to `True` by the error handler when a `Conflict` exception is received.
- Read by the CLI entry point after `run_polling()` returns to decide whether to exit with a non-zero code.
- Lifetime: process lifetime only; not persisted anywhere.

This is the only new state. No database migrations, no schema changes.
