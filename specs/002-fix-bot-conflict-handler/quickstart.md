# Quickstart: Verify Bot Conflict Handler

## Run the new unit tests

```bash
uv run pytest tests/integration/test_telegram_bot.py -k "conflict" -v
```

Expected: two new tests pass — one asserting shutdown on Conflict, one asserting continuation on non-Conflict errors.

## Run the full bot test suite

```bash
uv run pytest tests/integration/test_telegram_bot.py tests/integration/test_telegram_application_flow.py -v
```

All existing tests must continue to pass.

## Manual smoke-test (conflict detection)

1. Start the bot in one terminal:
   ```bash
   uv run finance bot
   ```
2. Start a second instance in another terminal:
   ```bash
   uv run finance bot
   ```
3. Within ~30 seconds, one instance must log:
   ```
   CRITICAL finance.bots.telegram.app — another bot instance is already running — shutting down
   ```
   and exit with a non-zero status (`echo $?` → non-zero).

## Manual smoke-test (dev.sh stale-kill)

1. Start the bot manually:
   ```bash
   uv run finance bot &
   BOT_PID=$!
   ```
2. Run the dev launcher:
   ```bash
   make run-all
   ```
3. Confirm in the output that `[dev] killing stale bot process $BOT_PID` appears before `[bot]` polling starts.
4. Confirm only one `finance bot` process is running:
   ```bash
   pgrep -f "finance bot"   # should return exactly one PID
   ```
