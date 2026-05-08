# AGENTS.md

This file is the canonical entry point for any agent (LLM or human) working
on this repository. It captures the **dev-lifecycle policy** every change
must follow. The full rationale lives in
`openspec/changes/dev-lifecycle-policy/`.

## Branch model

```
   feat/<slug>  ──squash──▶  dev  ──merge-commit──▶  main
```

- `main` is the released branch. Never push to it directly.
- `dev` is the integration buffer. Agents merge their PRs here when CI is green.
- `feat/<slug>` is a per-task branch owned by a single agent.

## How to start a task

1. **Use a per-agent worktree.** When invoking the Claude Code `Agent` tool,
   pass `isolation: "worktree"`. This creates an isolated `git worktree`
   for the agent so multiple agents can work in parallel without stepping
   on each other.
2. **Branch off `dev`**, not `main`. Branch name: `feat/<slug>`. The slug
   is short, lowercase, hyphen-separated, and Conventional-Commits-friendly
   (e.g., `feat/help-handler`, `feat/wise-pdf-confidence-scoring`).
3. **Rebase on `dev` before opening a PR**. Do not merge `dev` into your
   feature branch — rebase it. Resolve conflicts locally.
4. **Target `dev` in the PR**, never `main`, never another agent's branch.

## Conventional Commits

All commit messages and all PR titles MUST follow
[Conventional Commits](https://www.conventionalcommits.org/).

Allowed types: `feat`, `fix`, `chore`, `docs`, `refactor`, `test`, `ci`,
`build`, `perf`, `style`. Optional scope in parentheses, e.g.
`feat(bot): respond to /help`.

The local commit-msg hook (commitizen) blocks non-conformant messages.
The CI `pr-title` job blocks non-conformant PR titles.

## Merge strategy

| From → To              | Strategy      | Why                                                  |
|------------------------|---------------|------------------------------------------------------|
| `feat/<slug>` → `dev`  | **squash**    | one feature = one commit on `dev`; trivial to revert |
| `dev` → `main`         | **merge-commit** | preserves the boundary between promotion batches  |

`main` does **not** require linear history (it would forbid the merge-commit
promotion). `dev`'s history is the squashed-feature timeline; `main`'s
history is the promotion-batch timeline.

## Who can merge what

| PR target | Who may merge                          | Required signals                |
|-----------|----------------------------------------|----------------------------------|
| `dev`     | the PR author (including LLM agents)   | all CI status checks green       |
| `main`    | a human reviewer (Joshua) only         | all CI status checks green **and** 1 approving review |

This is the rule that makes the `dev` buffer pay rent: agents keep moving
without blocking on human availability, and the human's attention is
reserved for promoting batches from `dev` to `main`.

## Tests are the review artifact

The human reviewer reads the **tests** to decide whether to promote a
feature from `dev` to `main`. Implementation is glanced at; tests are
read carefully. Write tests with that reader in mind.

- **Structure**: GIVEN / WHEN / THEN. Make the structure visible — in
  test names (`test_when_pdf_uploaded_then_drafts_appear`), in docstrings,
  or as block comments inside the test body.
- **Reads as a spec**: a test file should describe a feature's behavior
  when read top-to-bottom.
- **Prefer integration over heavy mocking** when the cost is comparable.
  A passing mock-heavy unit test that doesn't exercise the real flow is
  low review-value.
- **Match OpenSpec scenarios.** Existing capability specs already use
  GIVEN / WHEN / THEN scenarios; tests should mirror those scenarios so
  the spec, the tests, and the review artifact share one structure.

A PR's tests should make it possible for the reviewer to answer two
questions by reading the test files alone:

1. *Does this describe a feature I want?*
2. *Do these tests pass?*

If both answers are yes, the feature is greenlit for promotion to `main`.

## Local hooks (run on every commit)

Configured in `.pre-commit-config.yaml`. Hooks are deliberately fast
(sub-5-second target) so contributors do not reach for `--no-verify`.

- `ruff format` and `ruff check --fix` — formatting and basic lint
- `trailing-whitespace`, `end-of-file-fixer`, `check-yaml`, `check-toml`,
  `check-merge-conflict`, `check-added-large-files`
- `gitleaks` — secret scan over staged content
- `commitizen` (commit-msg stage) — Conventional Commits format

First-time setup on a fresh clone:

```bash
make sync     # uv sync --all-groups (installs pre-commit + commitizen)
make hooks    # uv run pre-commit install --install-hooks
```

## CI gates (run on every push and PR)

Configured in `.github/workflows/ci.yml`. CI runs on pushes to `feat/**`,
`dev`, and `main`, and on every PR targeting `dev` or `main`.

| Job        | What it runs                                            |
|------------|----------------------------------------------------------|
| `lint`     | `ruff format --check` and `ruff check`                   |
| `typecheck`| `mypy src` (strict on `finance.core.*`, lax elsewhere)   |
| `test`     | `pytest --cov=finance --cov-branch`; uploads coverage   |
| `web-build`| builds the React + Vite UI (`src/finance/web`)           |
| `secrets`  | `gitleaks` over full history                             |
| `pr-title` | Conventional Commits check on the PR title (PRs only)    |

All required jobs must be green before a PR can merge to `dev` or `main`.

## Coverage policy

Coverage is **collected** in CI (uploaded as an artifact) but **not
gated** in v1. Per-module floors are placeholders mirroring the mypy
strictness gradient (strict in `finance.core.*`, lax elsewhere).

The placeholders are documented as comments in `pyproject.toml`'s
`[tool.coverage.report]` section. The first change after this one that
adds meaningful new tests for a module SHALL set that module's floor to
its post-change measured coverage and convert the placeholder into an
enforced threshold. Floors only ratchet upward.

## Manual smoke checks

A small number of surfaces cannot be exercised meaningfully in CI (they
require real third-party credentials and network egress). For those,
each change that touches the surface MUST be followed by the documented
manual smoke check before opening the `dev → main` promotion PR.

- After any change touching `src/finance/bots/telegram/` or
  `src/finance/cli/app.py::bot_cmd`, run the Level-3 smoke check from
  `openspec/changes/fix-telegram-bot-silent-failures/tasks.md` (§5)
  against your own bot token and chat id before promoting `dev → main`.

## What this file does NOT cover

- Code style beyond what ruff enforces (no per-file style rules).
- Architecture and per-capability conventions — see
  `openspec/specs/` (after archive) and `docs/architecture.md`.
- The list of v1 non-goals — see the bootstrap proposal at
  `openspec/changes/bootstrap-finance-app/proposal.md` and `README.md`.

## Quick reference: starting a new change

```
1. /opsx:propose <short-description>      # or /opsx:explore to think first
2. (Claude creates proposal/design/specs/tasks)
3. /opsx:apply <change-name>              # implements tasks
4. Open PR feat/<slug> → dev              # CI gates merge
5. (later) Open PR dev → main             # human approval gates merge
6. /opsx:archive <change-name>            # after the dev → main merge ships
```
