# Tasks: Fix Telegram Bot Conflict Error Handler

**Input**: Design documents from `specs/002-fix-bot-conflict-handler/`

**Prerequisites**: plan.md, spec.md, research.md, contracts/error-handler.md

**Tests**: Included — spec explicitly requires a unit test for the error-handler branch (TDD: write failing test first).

**Organization**: Two independent user stories; no shared foundational setup required — all changes are purely additive to existing files.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to

---

## Phase 3: User Story 1 — Bot exits cleanly on Conflict (Priority: P1) 🎯 MVP

**Goal**: Register a PTB error handler that shuts the bot down with a CRITICAL log when a 409 Conflict is received, and continues normally for all other errors.

**Independent Test**: Invoke `_on_error` directly with a mock Conflict context; assert `stop()` called once. Invoke with a non-Conflict error; assert `stop()` never called. Both tests runnable without a live Telegram connection.

### Tests for User Story 1 ⚠️ Write FIRST — confirm FAIL before implementing

- [x] T001 [US1] Add failing test `test_on_error_conflict_shuts_down_and_logs_critical` in `tests/integration/test_telegram_bot.py` — mock context with `context.error = telegram.error.Conflict("test")`, `context.application.stop = AsyncMock()`, call `_on_error(None, context)`, assert `stop` awaited once and CRITICAL record contains "another bot instance"
- [x] T002 [P] [US1] Add failing test `test_on_error_non_conflict_continues_and_logs_error` in `tests/integration/test_telegram_bot.py` — mock context with `context.error = RuntimeError("boom")`, assert `stop` never called and ERROR record exists

### Implementation for User Story 1

- [x] T003 [US1] Add module-level `_conflict_seen: bool = False` flag and async `_on_error(update, context)` function in `src/finance/bots/telegram/app.py` — on Conflict: set flag, log CRITICAL "another bot instance is already running — shutting down", schedule `asyncio.get_running_loop().create_task(context.application.stop())`; on other errors: log ERROR with `exc_info=context.error`
- [x] T004 [US1] Register the handler in `build_application()` in `src/finance/bots/telegram/app.py` — add `application.add_error_handler(_on_error)` after existing `add_handler` calls; also reset `_conflict_seen = False` at the top of `build_application()` to keep tests isolated
- [x] T005 [US1] Add exit-code guard in `src/finance/cli/app.py` — after `application.run_polling(stop_signals=None)`, import `_conflict_seen` from `finance.bots.telegram.app` and call `sys.exit(1)` if it is True

**Checkpoint**: Run `uv run pytest tests/integration/test_telegram_bot.py -k "conflict" -v` — both new tests must pass and all existing bot tests must remain green.

---

## Phase 4: User Story 2 — Dev launcher kills stale bot (Priority: P2)

**Goal**: `scripts/dev.sh` detects and kills any already-running `finance bot` process before starting a new one, preventing the Conflict condition from arising during development.

**Independent Test**: Manually start `uv run finance bot &`; then run `make run-all`; confirm `[dev] killing stale bot process <pid>` appears in output and only one bot process is running afterward.

### Implementation for User Story 2

- [x] T006 [P] [US2] Add pgrep stale-kill guard in `scripts/dev.sh` — insert before the `if [[ "$RUN_BOT" == "1" ]]; then` block:
  ```bash
  if command -v pgrep &>/dev/null; then
    stale=$(pgrep -f "finance bot" 2>/dev/null | grep -v "^$$\$" || true)
    if [[ -n "$stale" ]]; then
      echo "[dev] killing stale bot process $stale"
      kill "$stale" 2>/dev/null || echo "[dev] warning: could not kill stale bot process $stale"
      sleep 0.5
    fi
  fi
  ```

**Checkpoint**: Both user stories now complete. Run `uv run pytest tests/integration/test_telegram_bot.py -v` to confirm all tests pass.

---

## Final Phase: Polish & Validation

- [x] T007 Run full test suite and confirm no regressions: `uv run pytest --tb=short -q`
- [x] T008 [P] Verify quickstart smoke-test steps from `specs/002-fix-bot-conflict-handler/quickstart.md` can be followed manually (or confirm via test run)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 3 (US1)** and **Phase 4 (US2)** are fully independent — they touch different files and can be done in any order or in parallel.
- **Final Phase**: Depends on both US1 and US2 being complete.

### User Story Dependencies

- **US1 (P1)**: No prerequisites beyond the existing codebase. Tests (T001–T002) must be written and confirmed failing before T003–T005.
- **US2 (P2)**: No prerequisites; can be done entirely in parallel with US1.

### Within US1

- T001 and T002 (tests) can be written in parallel — they target the same file but are independent functions.
- T003 must complete before T004 (the handler must exist before it can be registered).
- T004 must complete before T005 (the flag must be set by T003/T004 before the CLI reads it).

### Parallel Opportunities

- T001 and T002 are parallel (both test writing, same file, non-overlapping functions).
- T006 (US2) can be done in parallel with any US1 task since it touches only `scripts/dev.sh`.

---

## Parallel Example: User Story 1

```bash
# Write both failing tests in parallel (different functions, same file):
Task T001: "test_on_error_conflict_shuts_down_and_logs_critical in tests/integration/test_telegram_bot.py"
Task T002: "test_on_error_non_conflict_continues_and_logs_error in tests/integration/test_telegram_bot.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only — 4 tasks)

1. Write failing tests T001–T002
2. Implement T003 (`_on_error` function)
3. Register T004 (`add_error_handler`)
4. Add exit guard T005 (CLI)
5. **STOP and VALIDATE**: both new tests pass, all existing bot tests green

### Incremental Delivery

1. Complete US1 → Bot is safe against duplicate-instance Conflict — **SHIP**
2. Complete US2 → Dev workflow hardened against stale processes — **SHIP**

### Single-Developer Order

T001 → T002 → T003 → T004 → T005 → T006 → T007 → T008

---

## Notes

- `_conflict_seen` is a module-level mutable — reset it at the top of `build_application()`, not just at module load, so each test that calls `build_application()` gets a clean slate.
- `pgrep -f "finance bot"` may match the `grep` process itself on some Linux variants; the `grep -v "^$$\$"` filter removes the current shell's PID to prevent self-kill. Verify this works on the target platform.
- Do not skip pre-commit hooks when committing.
