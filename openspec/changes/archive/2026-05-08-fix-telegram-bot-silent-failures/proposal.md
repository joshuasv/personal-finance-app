## Why

The user reported the Telegram bot was silent on every input: `/help` got no reply, a PDF upload got no reply, and the launching terminal showed no log output. The existing test suite was passing (151 tests green, including telegram tests), so this looked like a class of failure the tests structurally couldn't see — they call handler functions directly with mocked `Update`/`Context`, bypassing handler registration, filter matching, dispatcher routing, polling startup, and the network surface entirely.

Investigation produced a more honest picture, and this change addresses all of it:

1. **The original symptom was operator error.** `finance serve` (REST/MCP) was being run instead of `finance bot` (Telegram poller) — they're separate, independent processes. The README's "End-to-end manual checklist" actively misled the operator: step 3 says to run `finance serve` and step 5 says "send a Wise statement to your bot," with no mention that `finance bot` must also be running. With no poller listening, all three symptoms (no reply, no logs, no `~/.finance/inbox/` folder) follow trivially.
2. **One real but unrelated bug surfaced during investigation.** The `document_handler` mime check rejected `application/octet-stream` even when the filename was `*.pdf`. Telegram emits this for some clients (notably iOS). This bug was masked by the original-symptom confusion and would have blocked PDF ingestion for anyone using those clients.
3. **The original concern about the test surface was right, even if the immediate failure was operator error.** No automated test could distinguish "bot is broken" from "bot was never started" from the operator's perspective. The next failure of this shape might be a real code bug; CI couldn't tell, and a single-user app can't afford a manual-only verification floor.

## What Changes

- **Level-2 dispatcher tests** (`tests/integration/test_telegram_application_flow.py`) — build the actual `python-telegram-bot` `Application` via `build_application(...)`, dispatch synthetic `Update` payloads through `Application.process_update(...)`, and assert what handlers send back. Five tests cover `/help`, the canonical-mime PDF path, the `application/octet-stream` PDF path, the disallowed-chat audit-log path, and a handler-registration sanity check.
- **Level-3 real-Telegram E2E suite** (`tests/e2e_telegram/`) — gated, opt-in. Spawns `finance bot` as a subprocess with an isolated `FINANCE_HOME`, waits for the "bot ready" log line (failure is loud, with the captured bot stdout/stderr attached to the assertion), then drives a Telethon user-account client to send `/help`, `/balance`, `/drafts`, and a real Wise PDF (with the picker click-through) over real Telegram. Five tests; ~18s end-to-end. Skipped unless `.telegram-test-secrets.toml` and the user's `~/.finance/config.toml` provide the needed credentials.
- **Document handler fix** — `_looks_like_pdf(mime_type, file_name)` accepts `application/pdf` and `application/octet-stream`+`*.pdf`. Pinned by Level-2 test 2.3 and Level-3 PDF flow test.
- **Logging architecture cleanup** — moved `configure_logging(settings)` from `build_application` into `bot_cmd`, mirroring `serve_cmd`. The previous code also called `configure_logging` (inside `build_application`), so this change is structural rather than a runtime fix; CLI commands now own their own logging setup at one layer.
- **README fix** — patched the manual checklist so step 3 mentions `finance bot` alongside `finance serve`, and added a one-line note that the surfaces are independent processes. Without this, the failure trap that triggered this change recurs for every new operator.
- **AGENTS.md backstop note** — kept the "Manual smoke checks" section as a fallback for environments where the E2E credentials aren't available, but the E2E layer is now the primary path.
- **Telethon as a dev dependency** + a one-time auth helper (`scripts/telethon_auth.py`) that produces a `StringSession`. Documented in the conftest docstring.

## Capabilities

### New Capabilities
<!-- None — both touched capabilities already exist. -->

### Modified Capabilities
- `telegram-bot`: added a requirement that every handler is invokable end-to-end via `Application.process_update(...)`; modified the existing "Telegram bot process" requirement to specify that logging is configured before polling starts.
- `cli`: modified "Serve and bot commands" so that `finance bot` configures logging the same way `finance serve` does.

## Impact

- **Code**:
  - `tests/integration/test_telegram_application_flow.py` (new, 5 tests + sanity check)
  - `tests/e2e_telegram/{conftest.py,test_telegram_e2e.py,__init__.py}` (new, 5 tests, gated)
  - `tests/integration/test_cli.py::test_bot_configures_logging_before_polling` (new)
  - `src/finance/cli/app.py::bot_cmd` (calls `configure_logging` before `build_application`)
  - `src/finance/bots/telegram/app.py::build_application` (no longer calls `configure_logging`)
  - `src/finance/bots/telegram/handlers.py` (`_looks_like_pdf` helper; broadened mime acceptance in `document_handler`)
  - `scripts/telethon_auth.py` (new, ~80 lines, interactive)
  - `pyproject.toml` (telethon dev dep; new `e2e_telegram` marker)
  - `.gitignore` (`.telegram-test-secrets.toml`)
  - `AGENTS.md` ("Manual smoke checks" section)
  - `README.md` (manual checklist fix + surfaces-are-independent note)
- **Dependencies**: adds `telethon>=1.36` to the dev group. No production deps change.
- **Risk**:
  - The Level-2 stub bot drifts from PTB's real `Bot` interface as PTB evolves. *Mitigation*: stub is minimal; PTB upgrade failures are loud, not silent.
  - The Level-3 suite depends on real Telegram and a real user account. *Mitigation*: gated by credential presence; skipped (not failed) when creds are missing; CI without secrets stays green. Test runs leave real messages in the operator's chat history with the bot.
- **Out of scope**: any non-bot surface; refactor of the handler architecture; new bot features (LLM bridge, free-form text). The README change is scoped to one section (manual checklist + a one-liner above the surfaces table) and does not touch architectural docs.
