## ADDED Requirements

### Requirement: Branch model is Gitflow-lite
The repository SHALL use three classes of branch: `main` (released), `dev` (integration buffer), and `feat/<slug>` (per-task). Pull requests from `feat/*` branches SHALL target `dev`. Pull requests from `dev` SHALL target `main`. No other branch flow is permitted.

#### Scenario: Feature PR targets dev
- **GIVEN** an agent has finished work on branch `feat/add-help-handler`
- **WHEN** the agent opens a pull request
- **THEN** the PR's base branch is `dev`, never `main`

#### Scenario: Promotion PR targets main
- **GIVEN** several feature PRs have merged to `dev` and are ready to ship
- **WHEN** a promotion PR is opened
- **THEN** the PR's base is `main` and its head is `dev`

### Requirement: Agents may auto-merge to dev on green CI
A pull request whose base is `dev` SHALL be mergeable by its author (including an LLM agent) the moment all required CI status checks pass. No human review SHALL be required to merge to `dev`.

#### Scenario: Agent merges its own PR to dev
- **GIVEN** an agent has opened a PR `feat/foo` → `dev` and CI is green
- **WHEN** the agent (or any other actor) clicks merge
- **THEN** the merge succeeds without requiring an approving review

#### Scenario: Failing CI blocks merge to dev
- **GIVEN** an agent has opened a PR `feat/foo` → `dev` and at least one CI check is failing
- **WHEN** any actor attempts to merge
- **THEN** the merge is blocked by branch protection until all checks pass

### Requirement: Promotion to main requires human approval
A pull request whose base is `main` SHALL require both (a) all required CI status checks passing and (b) at least one approving review from a human reviewer before it can be merged.

#### Scenario: Approval required for main
- **GIVEN** a PR `dev` → `main` with green CI but no approving review
- **WHEN** any actor attempts to merge
- **THEN** the merge is blocked by branch protection until a human approves

### Requirement: Pre-commit hooks run locally on every commit
Every commit on every branch SHALL pass a configured set of fast local hooks before the commit is created. The required hooks SHALL be: `ruff format`, `ruff check`, trailing-whitespace, end-of-file-fixer, YAML/TOML syntax checks, merge-conflict-marker check, large-file check, gitleaks secret scan, and a commitizen check on the commit message.

#### Scenario: Trailing whitespace blocks commit
- **GIVEN** the developer has staged a file with trailing whitespace
- **WHEN** the developer runs `git commit`
- **THEN** the pre-commit hook rewrites or reports the file and the commit does not complete until it is clean

#### Scenario: Secret-shaped string blocks commit
- **GIVEN** a staged file contains a string that gitleaks recognizes as a secret
- **WHEN** the developer runs `git commit`
- **THEN** the gitleaks hook fails the commit and prints the matched rule

#### Scenario: Non-Conventional commit message blocks commit
- **GIVEN** the developer types a commit message that is not Conventional Commits formatted (for example, "fix stuff")
- **WHEN** the commit-msg hook runs
- **THEN** the commit is rejected and the message format is explained

### Requirement: CI runs on every push and pull request
A GitHub Actions workflow SHALL run for every push to `feat/**`, `dev`, or `main`, and for every pull request targeting `dev` or `main`. The workflow SHALL include the following required jobs: lint (ruff format-check + ruff check), typecheck (mypy), test (pytest), web-build, secrets (gitleaks over full history), and pr-title (Conventional Commits validation, runs on `pull_request` events only).

#### Scenario: CI runs on a feature push
- **WHEN** a commit is pushed to a `feat/*` branch
- **THEN** the workflow runs all required jobs and reports their status on the commit

#### Scenario: PR title is non-conformant
- **GIVEN** a pull request titled "stuff"
- **WHEN** the `pr-title` job runs
- **THEN** the job fails with a message describing the Conventional Commits format

### Requirement: main and dev branches are protected
The `main` branch SHALL be configured with: require PR, require 1 approving review, require all CI status checks green, require branches up-to-date before merging, require linear history, disallow force-push, disallow direct push, disallow deletion. The `dev` branch SHALL be configured with: require PR, require all CI status checks green, disallow force-push, disallow direct push, disallow deletion. The `dev` branch SHALL NOT require an approving review.

#### Scenario: Direct push to main is rejected
- **WHEN** any actor attempts `git push origin main` from a local commit
- **THEN** the remote rejects the push, citing branch protection

#### Scenario: Force-push to dev is rejected
- **WHEN** any actor attempts `git push --force origin dev`
- **THEN** the remote rejects the push, citing branch protection

### Requirement: Per-agent worktree workflow is documented
The file `AGENTS.md` SHALL contain a section describing the per-agent worktree workflow, including: the `feat/<slug>` branch naming rule, the instruction to use Claude Code's `Agent` tool with `isolation: "worktree"`, the requirement that PRs target `dev`, and the rule to rebase on `dev` before opening a PR.

#### Scenario: New agent reads the convention
- **GIVEN** a new Claude Code session opens for this repository
- **WHEN** the agent reads `AGENTS.md`
- **THEN** the agent finds explicit instructions covering branch naming, worktree isolation, PR target, and rebase rule

### Requirement: Tests follow GIVEN/WHEN/THEN structure and serve as the review artifact
New tests SHALL be written using GIVEN/WHEN/THEN structure (in test names, docstrings, or block comments such that the structure is visible to a reader). Test files SHALL be organized so that reading the file describes the feature's behavior. The reviewer's primary signal for promoting a feature from `dev` to `main` is the readability and correctness of its tests.

#### Scenario: Test name reads as a behavior description
- **GIVEN** an agent is adding a test for a new behavior
- **WHEN** the test is written
- **THEN** the test name or its body makes the GIVEN/WHEN/THEN structure visible (for example, `test_when_pdf_uploaded_then_drafts_appear`)

#### Scenario: Reviewer reviews via tests
- **GIVEN** a PR `dev` → `main` covering a new feature
- **WHEN** the human reviewer reads the change
- **THEN** the reviewer can determine whether to approve based primarily on reading the new tests, supplemented by a sanity check of the implementation

### Requirement: Coverage is collected with placeholder per-module floors
Pytest SHALL be configured to produce a coverage report on every CI run. Per-module coverage floors SHALL be defined in `pyproject.toml` mirroring the existing mypy strictness gradient (strict in `finance.core.*`, lax elsewhere). v1 floors SHALL be permissive placeholders set so that current measured coverage passes them. CI SHALL upload the coverage report as an artifact but SHALL NOT fail builds on threshold violations in v1.

#### Scenario: Coverage report is produced
- **WHEN** the `test` job runs in CI
- **THEN** a coverage report is generated and uploaded as a workflow artifact

#### Scenario: Placeholder floor does not gate the build
- **GIVEN** a PR whose changes leave a non-`core` module's coverage below 50%
- **WHEN** CI runs
- **THEN** the test job passes (no gating in v1) but the coverage artifact reflects the new number

### Requirement: Coverage floor ratchets on the first new-test change per module
The first change after this one that adds meaningful new tests for a given module SHALL set that module's coverage floor to the post-change measured coverage and SHALL enable the coverage gate for that module from that point forward. The floor for a module SHALL never decrease.

#### Scenario: Ratchet activates on first test write
- **GIVEN** the placeholder floor for `finance.parser` is 0%
- **AND** a future change introduces 12 new tests covering `finance.parser`, raising measured coverage to 73%
- **WHEN** that change merges
- **THEN** the configured floor for `finance.parser` is updated to 73% and CI begins gating on it

#### Scenario: Floor cannot decrease
- **GIVEN** the configured floor for `finance.parser` is 73%
- **AND** a later change would lower measured coverage for `finance.parser` to 70%
- **WHEN** CI runs
- **THEN** the test job fails because the configured floor is exceeded downward

### Requirement: Conventional Commits enforced for commit messages and PR titles
All commit messages SHALL conform to Conventional Commits, enforced locally by a commit-msg hook. All pull request titles SHALL conform to Conventional Commits, enforced by a CI job that runs on every `pull_request` event.

#### Scenario: Commit message is conformant
- **GIVEN** a developer types `feat(bot): respond to /help`
- **WHEN** the commit-msg hook runs
- **THEN** the commit completes

#### Scenario: PR title is non-conformant blocks merge
- **GIVEN** a pull request titled "various fixes"
- **WHEN** the pr-title job runs
- **THEN** the job fails and (because it is a required check) the PR cannot be merged until the title is fixed
