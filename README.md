# finance

Local-first personal finance app. One Python core (the **operation registry**),
five surfaces that all dispatch into it: a CLI, a REST API, an MCP server, a
Telegram bot, and a React web UI. v1 ships the loop **"Wise PDF in →
reviewed transactions → monthly savings out."**

The architecture is intentionally additive: institution adapters, ingestion
sources, and operations are registry entries — adding a new bank, a new
report, or a new chat surface does not require touching `core/`.

## Quick start

```bash
make sync                        # install Python deps via uv
make hooks                       # install pre-commit hooks (first time only)
make test                        # run the full test suite
uv run finance --help            # browse the CLI
```

## Development workflow

This repo follows a Gitflow-lite branch model (`main` ◀ `dev` ◀ `feat/*`)
with auto-merge to `dev` for green PRs and human-gated promotion to
`main`. All commits and PR titles must follow Conventional Commits, and
local pre-commit hooks (ruff, gitleaks, commitizen) enforce formatting,
lint, secret scanning, and message format on every commit.

The full policy — branch model, merge strategies, agent worktree
workflow, CI gates, and the "tests as review artifact" principle — lives
in [`AGENTS.md`](./AGENTS.md). New contributors (human or LLM) should
read it once before starting their first change.

## Setup

1. **Install dependencies**

   ```bash
   uv sync --all-groups                    # Python
   npm --prefix src/finance/web install    # web UI
   ```

2. **Initialize the database**

   ```bash
   uv run finance init
   ```

   This creates `~/.finance/finance.db` and runs every Alembic migration to
   head. It's idempotent — re-running on an up-to-date database is a no-op.

3. **Configure secrets** (written to `~/.finance/config.toml` with mode `0600`)

   ```bash
   uv run finance config set api.key sk_live_someStrongRandomString
   uv run finance config set telegram.token "<bot token from @BotFather>"
   uv run finance config set telegram.allow_list 12345              # your chat id
   ```

   `finance config get api.key` shows a redacted value (`sk_live_…(N chars)`)
   so the raw key never lands on a terminal it shouldn't.

## Running the surfaces

Each surface below is its own independent process — start only the ones
you need, in their own terminal. `finance serve` (REST/MCP) and `finance
bot` (Telegram poller) do not start each other; if you want both at once,
run both.

| Surface       | Command                                | Notes                                                                    |
|---------------|----------------------------------------|--------------------------------------------------------------------------|
| REST + MCP    | `uv run finance serve`                 | FastAPI on `127.0.0.1:8000`; MCP transport mounted at `/mcp`.            |
| REST + UI     | `uv run finance serve --with-ui`       | Same, plus the built web UI from `src/finance/web/dist/`.                |
| Telegram bot  | `uv run finance bot`                   | Long-poll. Refuses to start with an empty `telegram.allow_list`.         |
| Web UI (dev)  | `npm --prefix src/finance/web run dev` | `:5173`, dev proxy forwards `/api/*` to FastAPI.                         |
| Web UI (prod) | `npm --prefix src/finance/web run build` | Produces `dist/`; served by `finance serve --with-ui`.                 |

## End-to-end manual checklist (Wise PDF → savings number)

1. `make sync && uv run finance init`
2. `uv run finance config set api.key <strong random>`; (optional)
   `uv run finance config set telegram.token …` and
   `uv run finance config set telegram.allow_list <your chat id>`.
3. Start the surfaces you'll use, each in its own terminal — they're
   independent processes:
   - REST/MCP API: `uv run finance serve`
   - Web UI (dev): `npm --prefix src/finance/web run dev`
   - Telegram bot: `uv run finance bot` *(required if you'll send a PDF
     from your Telegram client in step 5; without it, the bot is silent
     because no poller is running)*
4. Open the web UI at <http://localhost:5173>, paste the API key, create an
   account (e.g., "Wise EUR" / EUR).
5. **Import a PDF**: send a Wise statement to your bot in Telegram (needs
   `finance bot` running from step 3), or run
   `uv run finance import wise-pdf ./statement.pdf --account "Wise EUR"`.
6. **Review drafts**: open the web UI's Drafts view, or
   `uv run finance draft list` / `… draft confirm <id>`.
7. **See savings**: web UI's Summary view, or
   `uv run finance report monthly 2026-04`.

## v1 limitations and the documented backlog

These are deliberate non-goals of v1, called out in the design doc:

- **No categorization.** Transactions carry only date, payee, amount, memo.
  Category model + rules + ML labelling are a separate change.
- **One bank.** Only the Wise PDF adapter ships. Chase / Santander / Plaid /
  SimpleFIN are additive; each implements `InstitutionAdapter` and registers
  itself.
- **No voice/text ingestion.** The pipeline can absorb any
  `IngestionSource`; the v1 ingress is PDF only.
- **No LLM bridge in Telegram.** v1 is a deterministic dispatcher. A future
  change can route free-form text through a personal AI assistant via MCP.
- **No net-worth aggregation.** The Account model has no type or
  liability flag. A focused future change introduces `is_liability`.
- **No inbox GC.** Inbound PDFs persist at `~/.finance/inbox/<sha256>.pdf`
  forever; the user prunes manually.

See `openspec/changes/bootstrap-finance-app/proposal.md` for the full
backlog and design.md for the per-decision rationale.

## Repository layout

```
src/finance/
  core/           # domain models, services, ops registry, money/validators
  ingestion/      # InstitutionAdapter protocol + Wise PDF + pipeline
  reporting/      # monthly summary, balance snapshot
  api/            # FastAPI app + auth
  mcp/            # MCP server (shares the registry)
  cli/            # Typer entrypoint (`finance`)
  bots/telegram/  # Telegram dispatcher (auth, inbox, handlers)
  web/            # Vite + React + TS web UI (its own package.json)
tests/{unit,integration,contract,e2e,fixtures}
```

For the architectural tour, see [`docs/architecture.md`](docs/architecture.md).
For instructions on adding a new institution adapter or a new operation, see
[`docs/extending.md`](docs/extending.md).
