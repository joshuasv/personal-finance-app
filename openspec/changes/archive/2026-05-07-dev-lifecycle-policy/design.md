## Context

The repo is one commit old, has no remote yet, no CI, no hooks, and one human contributor (Joshua) plus an unknown but growing number of LLM agents that will open PRs in parallel. The current bottleneck is review throughput, not code generation. The dev lifecycle has to absorb that asymmetry: agents produce, humans review, and the review surface is the tests themselves.

The bootstrap change deliberately deferred all process tooling. Tooling itself (ruff, mypy, pytest) is configured in `pyproject.toml` and surfaced via Makefile targets, but nothing forces it to run. This change adds the enforcement layer.

Constraints:
- Single primary reviewer (one human). Anything that requires human attention must be deliberately scoped to high-signal moments.
- Multiple agents may run in parallel; their workflow must not require coordination beyond Git's normal merging.
- Local hooks must be **fast** (sub-5-second). Slow checks belong in CI; if pre-commit is slow, contributors learn to bypass it.
- The remote is GitHub. Branch protection, Actions, and PR-title checks are all GitHub-flavored.
- The repo is greenfield enough that policy can be set without grandfathering legacy patterns.

## Goals / Non-Goals

**Goals:**
- A merge to `main` is impossible without (a) a PR, (b) a green CI, and (c) explicit human approval.
- A merge to `dev` is automatic when CI is green; no human attention is required.
- Every commit on every branch passes formatting, basic lint, and secret scanning before it leaves the developer's machine.
- Every PR title and every commit message follows Conventional Commits.
- Tests are written in a form a human can read as a specification of behavior (GIVEN/WHEN/THEN).
- Coverage is collected from day one; a per-module floor exists in config but is permissive at v1, and ratchets up organically as tests are written.
- The agent collaboration workflow (worktrees, branch naming, PR target) is documented in one place (`AGENTS.md`).

**Non-Goals:**
- Trunk-based development or any model where `main` is the only long-lived branch. The `dev` buffer is intentional.
- End-to-end browser testing in CI in v1 (separate change).
- Automated semantic versioning, changelog generation, or release tagging.
- CODEOWNERS, required reviewers other than "one human approval," or any multi-reviewer model.
- Automated dependency-update bots (Renovate/Dependabot) — left to a follow-up.
- Enforcing the branch-naming convention via tooling. v1 documents it; CI gating is later work.
- Setting concrete coverage numbers up front. They are set on first contact (see Decision below).

## Decisions

### Decision: Gitflow-lite (`main` ◀ `dev` ◀ `feat/*`) over trunk-based
- **What**: Three classes of branch. `main` is the "shipped" branch. `dev` is an integration buffer where agent PRs accumulate. `feat/<slug>` is per-task. PRs always target `dev`. Promotions from `dev` to `main` happen via PR with human review.
- **Why**: With multiple agents producing PRs faster than the single human reviewer can read them, a buffer prevents partially-baked work from reaching `main` while still letting agents make forward progress. Trunk-based requires the human to gate every PR, which the project's parallelism goals make untenable. The buffer also makes it cheap to revert a noisy week — `main` stays clean.
- **Alternatives considered**:
  - *Trunk-based with feature flags*: simpler topology but every agent PR demands human attention; collapses under parallel agent throughput.
  - *Full Gitflow with release branches*: overkill for a single-user, no-release-cadence app.

### Decision: Agents auto-merge to `dev` on green CI; humans gate `dev` → `main`
- **What**: PRs targeting `dev` may be merged by their author (including an LLM agent) the moment CI is green. PRs targeting `main` require an explicit human approval and a green CI. Branch protection enforces this difference: `dev` requires only "status checks pass"; `main` additionally requires "1 approving review."
- **Why**: This is the rule that makes the `dev` buffer pay rent. Without it, the buffer is just a second branch with the same review demands. With it, agents can keep producing without blocking on human availability, and the human's attention is reserved for promoting batches of `dev` work to `main` — the moment where review actually adds value.
- **Alternatives considered**:
  - *Human review on every `dev` merge*: collapses `dev` into "main with extra steps."
  - *No `dev`, agents push directly to `main`*: requires either no review (unsafe) or human-on-every-PR (the bottleneck we are trying to relieve).

### Decision: Pre-commit local for fast hooks; mypy and tests in CI only
- **What**: Local pre-commit hooks: `ruff format`, `ruff check`, `trailing-whitespace`, `end-of-file-fixer`, `check-yaml`, `check-toml`, `check-merge-conflict`, `gitleaks`, and a `commit-msg` hook running `commitizen check`. CI runs the same lint checks (defense in depth) plus `mypy`, `pytest`, `pytest-cov`, web build, and `gitleaks` over full history.
- **Why**: The hard heuristic is "embarrassed to push" vs. "expensive to run." Format, basic lint, and secrets fall in the first bucket — they catch things you would not want in a PR at all, and they finish in seconds. Mypy and pytest fall in the second bucket: useful, but slow enough that running them on every commit teaches contributors to use `--no-verify`. Putting them only in CI keeps the local loop fast and the CI loop authoritative.
- **Alternatives considered**:
  - *Mypy in pre-commit*: rejected — observed to drive contributors toward `--no-verify`. The existing `[tool.mypy]` config in `pyproject.toml` (strict on `core.*`, lax elsewhere) already gives mypy plenty of teeth in CI.
  - *No pre-commit at all, only CI*: ruff is fast enough that running it locally is essentially free, and gitleaks running locally prevents credentials from ever entering Git history — not just from being merged.

### Decision: Conventional Commits enforced via commitizen + GitHub Action
- **What**: Commit messages and PR titles must follow Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`, `ci:`, `build:`, `perf:`, `style:`). Local enforcement via a `commitizen` `commit-msg` pre-commit hook. PR titles enforced in CI via `amannn/action-semantic-pull-request`.
- **Why**: Joshua confirmed CC typing overhead is acceptable, and CC unlocks future automation cheaply (semantic-release, changelog generation) without committing to it now. Enforcing both commit messages and PR titles avoids the common failure mode where one is checked and the other is not.
- **Alternatives considered**: Free-form messages (loses the future automation hook); enforce only PR titles (commits inside the PR drift, which matters when squash-merging is not the default).

### Decision: gitleaks for secret scanning, both local and CI
- **What**: `gitleaks` runs as a pre-commit hook on staged content (fast, blocks the commit if a secret is detected) and as a CI step over full history (catches secrets that slipped in before this policy existed or via `--no-verify`).
- **Why**: Telegram bot credentials are a real concern and have been called out explicitly in `feedback.txt`. Local-only catches the easy case; CI-full-history catches the determined-to-bypass case. Gitleaks is a single Go binary, has good defaults, and is trivial to wire into pre-commit.
- **Alternatives considered**: `detect-secrets` (works, but its allowlist workflow is more ceremony than gitleaks' inline `# gitleaks:allow` markers); custom regex (no).

### Decision: Tests are the human review artifact; GIVEN/WHEN/THEN is the structural form
- **What**: Test names and bodies are written in GIVEN/WHEN/THEN form. Test files are organized so that reading them top-to-bottom describes the feature's behavior. Integration and end-to-end tests are preferred over heavily mocked unit tests when the cost is comparable. The reviewer's primary signal is *"do these tests describe a feature I want, and do they pass?"*; if yes, the feature is greenlit for promotion to `main`.
- **Why**: Joshua's review bandwidth is the project's main constraint. Reading tests is faster than reading implementation, and a well-written test reads as the spec it implements. This dovetails with the existing OpenSpec convention (spec scenarios are already GIVEN/WHEN/THEN), so the spec, the tests, and the review artifact share one structure.
- **Alternatives considered**:
  - *Reviewer reads source code*: slower, less reliable; the human ends up checking the same correctness properties the tests already check.
  - *Mock-heavy unit tests*: high coverage, low review value — the test passes but says nothing about whether the feature works end-to-end.

### Decision: Per-module coverage floors with placeholders; ratchet on first write
- **What**: `pytest-cov` configuration sets per-module coverage thresholds mirroring the existing mypy strictness gradient: `finance.core.*` is the strict module; everything else is lax. v1 ships with **placeholder thresholds** that match measured coverage at the time this change is implemented (so CI does not regress) but are deliberately permissive — they are not aspirational targets. The trigger to set real numbers: **the first change after this one that adds meaningful new tests for a module sets that module's floor to its post-change measured coverage**, and the floor ratchets from there.
- **Why**: Pulling a number from the air ("80%!") rewards coverage-for-coverage's-sake and gets quietly lowered when it becomes inconvenient. Mirroring mypy's gradient says "we care more about correctness in `core` than in glue layers" honestly. The ratchet trigger ties policy activation to the natural moment when someone is already thinking about tests, instead of needing a dedicated "set thresholds" project.
- **Alternatives considered**:
  - *Single global floor*: rejected — incentivizes writing easy tests for low-value code to lift the average.
  - *No coverage at all in v1*: rejected — collecting it costs nothing, and we want the data when the ratchet trigger fires.
  - *Aspirational target now*: rejected — the test surface is too small for any number to be meaningful, and it would create immediate pressure to write tests for coverage rather than for the review-as-spec model above.

### Decision: Per-agent worktrees as a documented convention, not new infrastructure
- **What**: Each agent works in its own `git worktree` off `dev`. Branch name is `feat/<slug>` where the slug is short and Conventional-Commits friendly (no spaces, lowercase, hyphens). Claude Code's `Agent` tool uses `isolation: "worktree"` to manage the worktree lifecycle automatically. PRs target `dev` and are rebased on `dev` before opening. The convention lives in `AGENTS.md`.
- **Why**: Worktrees let multiple agents work concurrently without stepping on each other's checkouts. Claude Code already handles the mechanics; this change just writes down the convention so all agents (and future humans) follow it. Putting it in `AGENTS.md` (currently empty) makes it the canonical place future agents look first.
- **Alternatives considered**: Building a worktree-management script (over-engineering, given Claude Code's built-in support); leaving it undocumented (works for one agent, breaks down at parallelism > 1).

### Decision: Branch protection configured per branch — `main` strict, `dev` lighter
- **What**:
  - `main`: require PR, require 1 approving review, require all CI status checks green, require branches up-to-date before merging, no force-push, no direct push, no deletion.
  - `dev`: require PR, require all CI status checks green, no force-push, no direct push. **No** required review (this is the rule that lets agents auto-merge).
  - `feat/*`: no protection — agents own their feature branches.
- **Why**: This is the GitHub-side enforcement of the auto-merge-to-`dev` decision above. Settings are intentionally explicit so a future contributor (or another agent) can recognize the policy from the protection rules alone.
- **Alternatives considered**: Same protection on both branches (collapses the `dev` buffer model); no protection at all (relies purely on convention, which agents will not always honor); requiring linear history on `main` (rejected — incompatible with the merge-commit promotion strategy below, which we want for batch visibility).

### Decision: Merge strategies — squash into `dev`, merge-commit into `main`
- **What**: PRs from `feat/*` to `dev` are merged with **squash** (each feature becomes a single commit on `dev`). PRs from `dev` to `main` are merged with **merge-commit** (the merge into `main` preserves the boundary between promotion batches and keeps every squashed feature commit visible from `main`'s history). `dev` is **not** rebased onto `main`; promotions flow forward only.
- **Why**: Squash for `feat/*` → `dev` keeps `dev`'s history readable as "one feature per commit" — easy to revert a single misbehaving feature. Merge-commit for `dev` → `main` preserves the *batch* — a human reading `main`'s history sees clearly which set of features were promoted together, which is the unit of human review and the unit a hypothetical revert would need to operate on. Linear history on `main` is therefore explicitly disabled.
- **Alternatives considered**:
  - *Squash both levels*: collapses every promotion to one commit on `main`, hiding what was actually shipped.
  - *Merge-commit both levels*: bloats `dev`'s history with each feature's intermediate commits, hurting reviewability.
  - *Rebase merge for `dev` → `main`*: linearizes but loses the batch boundary the human reviewer relied on.

## Risks / Trade-offs

- **Risk**: Agents auto-merge a regression to `dev` that propagates pain when promoting to `main`. *Mitigation*: a single revert of the offending PR on `dev` is cheap; the full CI suite gates promotion; coverage-collection (even without floors) flags suspicious test loss.
- **Risk**: `dev` rots — too many agent PRs land, no human gets around to promoting. *Mitigation*: the `dev` → `main` PR is itself just a PR; an agent can prepare it, the human only has to approve.
- **Risk**: Pre-commit gets bypassed via `--no-verify` once it becomes painful. *Mitigation*: keep hooks fast (sub-5-second target); the CI-side full-history gitleaks scan catches secrets that slipped past locally; lint failures show up in CI anyway.
- **Trade-off**: Placeholder coverage thresholds mean v1 has effectively no coverage gate. Accepted in exchange for not pulling numbers from thin air. Risk diminishes naturally as the ratchet trigger fires.
- **Trade-off**: Conventional Commits adds typing friction now in exchange for future automation we have not committed to. Accepted because the friction is small and the option value is large.

## Migration Plan

This is a process-only change in a near-empty repo, but it has a sequencing constraint because the GitHub remote does not yet exist:

1. Land the local-only pieces first (pre-commit config, commitizen config, AGENTS.md content, coverage config). These work on `main` immediately because `main` itself is not yet protected.
2. Push to GitHub (creates the remote).
3. Push the `.github/workflows/ci.yml` and verify it runs.
4. Configure branch protection on `main` and create the `dev` branch from `main`.
5. Configure branch protection on `dev`.
6. From this point forward, the workflow is enforced. Subsequent changes follow the agent-on-`dev` flow.

The tasks list orders the work accordingly.

## Open Questions

<!-- Resolved during apply: merge strategy (squash → dev, merge-commit → main) is now a Decision above; feat/* branches remain unprotected; CI uses GitHub-hosted runners. -->

- *None at this time.* If a future change reveals one (e.g., self-hosted runner cost-pressure once e2e lands), capture it here or open a follow-up change.
