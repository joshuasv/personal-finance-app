## Context

The user reported the bot was silent on every input: `/help` produced no reply, a PDF upload produced no reply, the launching terminal showed no log lines, and `~/.finance/inbox/` was never created. All 151 existing tests passed — including the telegram integration and e2e tests. This was the smoking gun: the test surface was structurally unable to see this class of failure.

Today's telegram tests call handler functions directly:

```
   Today's tests:
       h.document_handler(update, context)   ◀── direct call

   What production does:
       Update arrives → Application dispatcher → MessageHandler filter
       matches → handler invoked → reply goes via bot.send_message
                  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                  None of this is exercised by a single test.
```

Any bug in handler registration, filter selection, allow-list type coercion, the polling loop itself, or the operator's launch path is invisible to CI.

## Goals / Non-Goals

**Goals:**
- Have automated tests, runnable in CI, that fail when the bot is broken from the user's perspective — at the dispatcher level (always-on) and at the real-Telegram level (gated, opt-in).
- Fix any concrete bugs the new tests surface.
- Make the operator's launch path obvious so "I forgot to start the bot" is no longer a silent failure mode.

**Non-Goals:**
- Adding new bot features (LLM bridge, free-form text handling). Out of scope.
- Refactoring the handler architecture. This change is a fix + a test layer, not a redesign.
- Changing the inbox flow, the ingestion pipeline, or any non-bot surface.

## Decisions

### Decision: Level-2 dispatcher tests as the always-on regression layer
- **What**: tests build the real `Application` via `build_application(settings, registry, session_maker)`, then dispatch synthetic `Update` objects through `Application.process_update(update)`. The `Bot` instance attached to the Application is replaced with a `_StubBot` that records calls. Assertions check what the bot tried to send back.
- **Why**: this is a layer where bugs can live silently. Existing tests cover handler logic; Level-3 (real Telegram) is gated. Level 2 catches: handler-registration bugs, filter mismatches, dispatcher routing, allow-list payload-shape mismatches against payloads shaped like Telegram's. The fidelity is roughly 75% of true E2E at <1s/test.
- **Alternatives considered**:
  - *More Level-1 tests*: would not have caught this bug or the next of its kind.
  - *Level-3 only*: requires real Telegram credentials, real network, real bot — too costly for every-push CI.

### Decision: Level-3 Telethon E2E suite as a gated higher-fidelity layer
- **What**: `tests/e2e_telegram/` runs Telethon as a USER-account MTProto client against a real `finance bot` subprocess against the real Telegram servers. Five tests covering startup, `/help`, `/balance`, `/drafts`, and the full PDF-upload picker flow. Marker `@pytest.mark.e2e_telegram`; skipped unless `.telegram-test-secrets.toml` and the user's existing `~/.finance/config.toml` provide credentials.
- **Why**: Level 2 cannot catch operator-facing failure modes — wrong binary on PATH, wrong launch command, double-poll, network-egress issues, real-Telegram payload changes, file-download CDN behavior. Level 3 catches all of these because it runs the *exact* binary the operator runs, the exact way they run it. The fixture's "bot ready" wait turns silent startup failures into deterministic test failures with the captured stdout/stderr attached.
- **Alternatives considered**:
  - *respx (HTTP-level interception)*: doesn't exercise auth, real network, or real Telegram payloads. A passing respx test against a broken `finance bot` binary on the operator's PATH would be a false green.
  - *Local Bot API server (Docker)*: adds Docker as a hard dev/CI dep, image is ~150–200 MB, admin-injection path is folklore-documented. Heavier than Telethon for less fidelity.
  - *Manual smoke check only*: doesn't scale. The user's complaint that "manual testing each fix doesn't scale" is the trigger for adding Level 3 in the first place.

### Decision: stub the `Bot` rather than mock HTTP via respx (Level-2)
- **What**: replace the Application's `bot` attribute with a thin stub class that captures calls to `send_message`, `edit_message_text`, `get_file`, etc., and returns the minimal shape the dispatcher needs.
- **Why**: respx works at the httpx level and would intercept PTB's outgoing requests, but it's an extra layer and ties the test to PTB's internal HTTP shape (which is private). A bot-attribute stub is what PTB itself uses in its own test suite and matches the public contract.

### Decision: bot-side credentials live in `~/.finance/config.toml`, not duplicated
- **What**: the E2E conftest reads bot token + allow-list via `Settings.load()` (the same path `finance bot` uses) and resolves the `@username` via Telegram's `getMe` API at fixture setup. The repo-local `.telegram-test-secrets.toml` carries only the Telethon-side creds (api_id, api_hash, session_string, user_id).
- **Why**: single source of truth. Rotating the bot or its allow-list automatically updates the test config. Two-file duplication is a footgun.

### Decision: `bot_cmd` configures logging before `run_polling` (architecturally, not as a runtime fix)
- **What**: `src/finance/cli/app.py::bot_cmd` calls `configure_logging(settings)` before invoking `build_application(...)`, mirroring `serve_cmd`. Removed the corresponding call inside `build_application`.
- **Why**: prior to this change, `build_application` did call `configure_logging`, so root-logger setup was already happening before `run_polling`. The move is a cleaner ownership boundary (CLI commands own their own logging setup), not a runtime bug fix. The "no log output at all" symptom in the original report turned out to be operator error (no bot process running at all), not a logging-misconfiguration bug.

### Decision: TDD strictly — failing tests first, fixes after
- **What**: tasks ordered so dispatcher tests are written first and observed to fail before any production code is touched. Each subsequent fix is paired with a passing test result.
- **Why**: the bug surface was unknown at the start. The tests are the source of truth — they tell us what is broken and what success looks like.
- **What it actually surfaced**: only test 2.3 (octet-stream PDF mime check) failed pre-fix. Tests 2.1, 2.2, 2.4, and 1.5 passed pre-fix. The diagnostic shortlist below was mostly wrong; see the postmortem.

## Diagnostic shortlist (informational; mostly wrong in retrospect)

This is the original guess at where the bug lived. Kept here as a record.

```
   1. allow-list integer-vs-string mismatch in Settings → AllowList
   2. MessageHandler filter wrong for the PDF (e.g., requires
      mime_type="application/pdf" but Telegram sometimes sends
      "application/octet-stream")              ◀── ONLY THIS WAS REAL
   3. bot_cmd's missing configure_logging hides the actual cause
      of a silent crash (most likely paired with one of 1/2)
   4. is_allowed silently drops on a payload shape we did not
      anticipate (effective_chat is None, etc.)
   5. run_polling's stop_signals=None has an unintended side effect
      on this Python/PTB version
```

Items #1, #4, #5: not surfaced by Level-2 or Level-3 tests; not pursued.
Item #2: real, fixed, pinned by tests 2.3 and the Level-3 PDF flow.
Item #3: not actually a bug. `build_application` was already calling `configure_logging`. The "no logs" symptom was operator error.

## Postmortem: the original symptom was operator error

The reported symptom (`/help` no reply, no logs, no inbox folder) was produced by running `uv run finance serve` instead of `uv run finance bot`. They are independent processes:

- `finance serve` → FastAPI REST + MCP, listens on `127.0.0.1:8000`. Touches no Telegram code.
- `finance bot` → Telegram long-poller, talks to api.telegram.org. Touches no HTTP-server code.

With no `finance bot` running, the bot-side log handler never attaches (no logs), `inbox_dir()` is never invoked (no folder), and Telegram queues `/help` indefinitely on its side (no reply). All three symptoms follow from one cause.

The trap was made worse by the README. Step 3 of "End-to-end manual checklist" says to run `finance serve`, and step 5 says "send a Wise statement to your bot," with no instruction to run `finance bot`. Anyone reading top-to-bottom hits the same wall.

This change patches the README so the next operator (including future-Joshua) does not repeat the trip. The Level-3 E2E suite is the durable safeguard: even if a similar trap reappears in docs, the test runs the same binary the same way and would fail loud.

## Test contract for the synthetic Update (Level-2)

The Level-2 tests submit `Update` objects shaped exactly as Telegram emits them, otherwise the dispatcher's filters do not match. Mandatory shape elements:

```
   Update(
       update_id=<positive int>,
       message=Message(
           message_id=<int>,
           date=<datetime>,
           chat=Chat(id=ALLOWED_CHAT, type="private"),
           from_user=User(id=ALLOWED_CHAT, is_bot=False),
           text="/help",                   # for slash-command tests
           entities=[BOT_COMMAND],         # required for CommandHandler match
           # OR document=Document(...)    # for PDF tests
       )
   )
```

Built using PTB's own dataclasses so PTB's filter logic accepts them as authentic. The bot must also be set on every nested object via `_attach_bot(update, application.bot)` — PTB v22's `set_bot` is non-recursive, so `CommandHandler.check_update` would otherwise raise `RuntimeError: This object has no bot associated with it` on `message.get_bot()`. The helper walks slot names from the MRO.

## Risks / Trade-offs

- **Level-2**: a hand-rolled `Bot` stub drifts from PTB's real `Bot` interface as PTB evolves. *Mitigation*: stub is minimal (only methods the tests touch); test failures on PTB upgrade are loud, not silent.
- **Level-3**: Telegram occasionally rate-limits user accounts that do nothing but talk to one bot. *Mitigation*: 5 tests, ~18s total, low traffic; per-test 30s timeout; the suite is gated to a small number of intentional runs (PR validation, pre-archive). Test runs leave real messages in the operator's chat history.
- **Trade-off**: Level-2 adds 5 tests, ~0.7s; Level-3 adds 5 tests, ~18s but only when creds are present. CI without secrets pays nothing.

## Open Questions

- *Resolved*: single combined Level-2 test file with one test per scenario.
- *Resolved*: bot-side credentials read from `~/.finance/config.toml`, not duplicated.
- *Future*: should the Level-3 suite run on every PR or only on `dev → main` promotion PRs? Answer depends on CI minute budget; default proposal is "every PR with secrets configured, skipped otherwise."
