## Why

The repo today has good per-tool config (ruff, mypy, pytest) and a Makefile, but **no enforcement**: there are no pre-commit hooks, no CI, no branch protection, and no documented workflow for agents working in parallel. The bootstrap change explicitly deferred this. With more than one agent expected to be opening PRs in parallel — and a single human (Joshua) acting as final reviewer — the project needs explicit guardrails before the next functional change lands. The review model is also unusual: **tests are the artifact the human reads to greenlight a feature**, which means tests must be expressive (GIVEN/WHEN/THEN scenarios) and the workflow must put them front and center.

## What Changes

- Adopt **Gitflow-lite** (`main` ◀ `dev` ◀ `feat/*`). Agents merge to `dev` on green CI without human review; humans gate every `dev` → `main` merge.
- Install a **pre-commit framework** with fast, local-only hooks: `ruff format`, `ruff check`, whitespace/EOF/yaml/toml/merge-conflict, **gitleaks** secret scan, and a **commit-msg** hook enforcing **Conventional Commits** via commitizen.
- Push slow checks to **GitHub Actions CI**: lint, `mypy`, `pytest`, web build, gitleaks (full history), PR-title CC check. CI runs on every push to `feat/*`, `dev`, `main`, and on every PR.
- Enable **branch protection** on `main` (PR required, human review required, CI green, no force-push, linear history) and a lighter rule on `dev` (CI green, no force-push; agents may self-merge).
- Document a **per-agent worktree workflow** in `AGENTS.md` (currently empty): branch name `feat/<slug>`, use Claude Code's `isolation: "worktree"`, PRs always target `dev`, rebase before opening.
- Establish **tests-as-review-surface** as a project principle: tests use GIVEN/WHEN/THEN, are readable as specifications, and are what the human reviewer evaluates.
- Set up **coverage collection** in CI with **per-module floors** mirroring mypy strictness (`finance.core.*` strict, others lax). v1 ships with **placeholder thresholds** — actual numbers are set the first time a future change adds meaningful new tests for a module ("ratchet on first write").

## Capabilities

### New Capabilities
- `dev-lifecycle`: The branching model, local hooks, CI gates, branch protection, agent-collaboration workflow, test-style requirements, and coverage policy that govern how every future change to this repository is produced and merged.

### Modified Capabilities
<!-- None — this capability did not exist before. -->

## Impact

- **Code**: Adds `.pre-commit-config.yaml`, `.github/workflows/ci.yml`, a `commitizen` config block in `pyproject.toml`, and content in `AGENTS.md` (currently empty). Adds a coverage configuration (with placeholder per-module floors) but does not change application code.
- **Dependencies**: Adds dev-only `pre-commit` and `commitizen`. Installs `gitleaks` via the official pre-commit hook (binary fetched at hook-install time). No production runtime changes.
- **Workflow / process**: Every commit now runs hooks; bypassing them (`--no-verify`) is disallowed by convention. Every push triggers CI. `main` and `dev` become non-pushable directly; all changes flow through PRs.
- **GitHub setup (manual, one-time)**: Pushing this branch creates the GitHub remote; branch-protection rules on `main` and `dev` must be configured in the GitHub UI (or via `gh api`) once the remote exists. The change documents the required settings.
- **Out of scope (explicit backlog)**: end-to-end browser tests in CI (needs Playwright + browser infra); semantic-release and changelog automation; CODEOWNERS and required reviewers beyond the single human; Renovate/Dependabot for dependency updates; automated branch-name regex enforcement (handled by convention in v1); concrete coverage numbers (set on first new-test change per module, see design).
