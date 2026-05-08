## 1. Test scaffolding (the failing-tests-first phase)

- [x] 1.1 Create `tests/integration/test_telegram_application_flow.py` with `pytestmark = pytest.mark.integration`
- [x] 1.2 Add a test-only `_StubBot` class capturing `send_message`, `edit_message_text`, `get_file`, etc. The stub stores sent messages in a list the tests assert against
- [x] 1.3 Add helpers `_build_text_update(chat_id, text)` and `_build_document_update(chat_id, file_id, file_name, mime_type)` that produce real `python-telegram-bot` `Update` objects (not MagicMocks)
- [x] 1.4 Add a fixture that calls `build_application(settings, registry, session_maker)`, swaps the `application.bot` for a `_StubBot`, and yields `(application, stub_bot)`
- [x] 1.5 Sanity-check: assert that `application.handlers` contains the expected `MessageHandler`s and `CommandHandler`s after construction (catches the "handler never registered" failure mode without dispatching anything)

## 2. The failing tests (run before any fix; they should fail)

- [x] 2.1 `test_when_allowed_chat_sends_help_then_bot_replies_via_dispatcher` — dispatch a `/help` Update through `application.process_update(update)`; assert the stub bot received exactly one `send_message` whose text contains "Commands"
- [x] 2.2 `test_when_allowed_chat_sends_pdf_then_bot_replies_with_picker` — dispatch a document Update with `mime_type="application/pdf"`; assert the stub bot received a `send_message` with "PDF saved" and an inline keyboard `reply_markup`
- [x] 2.3 `test_when_allowed_chat_sends_pdf_with_octet_stream_mime_then_bot_still_handles_it` — same as 2.2 but `mime_type="application/octet-stream"` (Telegram does this for some PDFs); this test documents whether the bug includes the filter-too-strict variant
- [x] 2.4 `test_when_disallowed_chat_sends_help_then_bot_does_not_reply_and_logs_audit_line` — dispatch a `/help` from a non-allow-listed chat; assert no `send_message` was sent AND a single audit log line was emitted (caplog)
- [x] 2.5 Captured failure (initial run, pre-fix):
  ```
  FAILED tests/integration/test_telegram_application_flow.py::test_when_allowed_chat_sends_pdf_with_octet_stream_mime_then_bot_still_handles_it
  AssertionError: expected 'PDF saved' reply for octet-stream PDF, got:
    'v1 only accepts PDF statements. Use the CLI or web UI for other formats.'
  ```
  Tests 2.1, 2.2, 2.4 and 1.5 PASS pre-fix in the test environment (Python 3.12, python-telegram-bot 22.7). The dispatcher is wired correctly for slash commands and canonical-mime PDFs; only the document handler's mime filter is too strict.
- [x] 2.6 Failure mode (as it manifests):
  - Test 2.3 fails because `document_handler` rejects any document whose `mime_type != "application/pdf"`. Telegram sometimes emits `application/octet-stream` (especially on iOS / for files transferred from third-party clients) even for genuine PDFs; the bot replies "v1 only accepts PDF statements" and never invokes ingestion. This corresponds to diagnostic shortlist item #2 in `design.md`.
  - Items #1, #4, #5 from the diagnostic shortlist are not surfaced by these tests in the current dependency pin, so they are not pursued.
  - The "no log output at all" symptom (item #3) is addressed structurally in §3 by moving `configure_logging` ownership to the CLI command (mirroring `serve_cmd`).

## 3. Fix logging in `finance bot`

- [x] 3.1 In `src/finance/cli/app.py::bot_cmd`, call `configure_logging(settings)` after `load_settings()` and before `build_application(...)`, mirroring `serve_cmd`'s pattern. Removed the duplicate `configure_logging` call from `build_application` so logging ownership lives at one layer (the CLI), as `design.md` decided.
- [x] 3.2 Added `test_bot_configures_logging_before_polling` in `tests/integration/test_cli.py`: monkeypatches `configure_logging`, `build_application`, and a stub `run_polling` to assert the call order is `configure_logging → build_application → run_polling`.
- [x] 3.3 Re-ran §2 tests after the logging change; same one failure (test 2.3) — confirmed the logging change is structural, not the root cause.

## 4. Fix the root cause(s) the failing tests reveal

- [x] 4.1 Diagnosis: only test 2.3 fails. The captured assertion in §2.5 plus log output point to **diagnostic shortlist item #2** in `design.md`: the document handler's mime-type check is too strict.
- [x] 4.2 Applied the smallest fix in `src/finance/bots/telegram/handlers.py`: replaced the inline `mime_type != "application/pdf"` guard in `document_handler` with a `_looks_like_pdf(mime_type, file_name)` helper that also accepts `application/octet-stream` when the filename ends in `.pdf`. This is the in-handler form (kept the registration as `filters.Document.ALL` so we can give the user a clear "v1 only accepts PDF" message for genuinely-non-PDF docs).
- [x] 4.3 All five tests in §2 pass.
- [x] 4.4 Full suite green: `157 passed in 16.68s` (was 152; +5 new dispatcher tests).

## 5. Manual Level-3 smoke check (superseded by §8 but performed once for closure)

> Manual smoke check performed once by Joshua against the real bot to close the loop on the originally reported symptoms. Going forward, `tests/e2e_telegram/` (§8) is the durable verification path; this manual sequence is preserved in `AGENTS.md` only as a fallback for environments without E2E credentials.

- [x] 5.1 With a real bot token configured and `telegram.allow_list` set to your own chat id, run `finance bot` in one terminal — confirmed working
- [x] 5.2 Send `/help` to the bot from your Telegram client; observe a reply within ~2s — confirmed
- [x] 5.3 Send a Wise PDF statement; observe the adapter-picker prompt within ~5s — confirmed (octet-stream PDFs now accepted thanks to §4 fix)
- [x] 5.4 Pick the adapter, then the account; confirm the "Batch #N: M drafts" message arrives — confirmed
- [x] 5.5 Close the terminal; confirm logs were emitted at INFO level throughout (including a "bot ready" or equivalent line at startup) — confirmed

## 6. Workflow doc (optional, lightweight)

- [x] 6.1 Added a "Manual smoke checks" section to `AGENTS.md` pointing at this change's §5 / §8.
- [x] 6.2 No CI automation for the manual smoke check; documented as developer responsibility. CI automation now lives in §8 (real-Telegram E2E suite, gated by credential presence).

## 7. README fix (root cause of the original report)

The original "bot is silent" report was triggered by running `finance serve` instead of `finance bot`. The README's manual checklist actively misled the operator: step 3 says to run `finance serve` and step 5 says "send a Wise statement to your bot," with no instruction that `finance bot` must also be running. Without this fix, the same trap recurs for every new operator.

- [x] 7.1 Patched `README.md` step 3 of "End-to-end manual checklist" to mention `finance bot` alongside `finance serve`.
- [x] 7.2 Added a one-line note above the surfaces table making it explicit that the surfaces are independent processes — run only the ones you need.

## 8. Real-Telegram E2E test suite (replaces §5)

The user pushed back on §5 with "manual testing each fix doesn't scale." This section captures the durable replacement: a Telethon-driven E2E suite that exercises the exact same code path a human user hits, including the `finance bot` CLI, the polling loop, the network surface, and the file-download CDN.

- [x] 8.1 Added `telethon>=1.36` to the dev dependency group.
- [x] 8.2 Registered `e2e_telegram` pytest marker in `pyproject.toml` with a docstring explaining the gating.
- [x] 8.3 Created `scripts/telethon_auth.py`: one-time interactive auth helper that prompts for phone + Telegram code (+ 2FA if set), produces a `StringSession`, writes it to repo-local `.telegram-test-secrets.toml` (mode 0600), and prints CI-secret guidance.
- [x] 8.4 Added `.telegram-test-secrets.toml` to `.gitignore`.
- [x] 8.5 Created `tests/e2e_telegram/conftest.py`:
  - Telethon-side creds (`api_id`, `api_hash`, `session_string`, `user_id`) loaded from `.telegram-test-secrets.toml` + env overrides.
  - Bot-side creds (`bot_token`, `allow_list`) loaded via `Settings.load()` — same path `finance bot` uses; **no duplication**.
  - Bot `@username` resolved at fixture setup via Telegram's `getMe` API.
  - `bot_process` fixture: writes a fresh `config.toml` (mode 0600), runs `finance init`, creates one test account, drains pending Bot API updates, spawns `finance bot` as a subprocess, waits up to 30s for "bot ready" in stdout. On timeout, the captured bot stdout/stderr is attached to the failure message — silent startup failures become loud.
  - `tg_client` fixture: connected Telethon `TelegramClient` with the saved `StringSession`.
  - Sanity check: refuses to run if the Telethon `user_id` is not in the bot's `allow_list` (would otherwise time out silently).
- [x] 8.6 Created `tests/e2e_telegram/test_telegram_e2e.py` with five tests:
  - `test_when_bot_starts_then_terminal_is_not_silent` — proves "bot ready" appeared in the log within 30s.
  - `test_when_user_sends_help_then_bot_replies_with_commands_list` — Telethon sends `/help`; asserts reply contains "Commands".
  - `test_when_user_sends_balance_then_bot_lists_seeded_account` — `/balance` reply names the seeded account.
  - `test_when_user_sends_drafts_on_fresh_db_then_bot_says_no_drafts`.
  - `test_when_user_uploads_pdf_then_bot_walks_through_picker_to_drafts` — sends a real Wise PDF as a document, clicks the adapter button, clicks the account button, asserts final reply contains `"Batch #"` and `"drafts"`.
- [x] 8.7 Confirmed all five E2E tests pass against the real bot: `5 passed in 18.14s`. Full suite: `162 passed in 34.17s` (157 pre-existing + 5 new E2E; the 5 Level-2 tests were already counted in the 157).
