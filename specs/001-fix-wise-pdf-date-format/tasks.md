---
description: "Task list for Parse Wise PDF dates in a general, locale-tolerant form"
---

# Tasks: Parse Wise PDF dates in a general, locale-tolerant form

**Input**: Design documents from `specs/001-fix-wise-pdf-date-format/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/wise-date-line.md, quickstart.md

**Tests**: INCLUDED. The spec mandates a regression fixture and parametrized
tests (FR-005, FR-007), and AGENTS.md treats tests as the review artifact, so
test tasks are first-class and written before the implementation they cover.

**Organization**: Grouped by user story. US1 (P1) is the MVP — it fixes the
reported bug. US2 (P2) hardens against silent failures.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1 = locale-tolerant parsing, US2 = fail-loud-on-empty

## Path Conventions

Single Python project: source in `src/finance/`, tests in `tests/`. All paths
below are repository-relative.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish the failing baseline so the fix is provably effective.

- [X] T001 Confirm the bug baseline: run the repro from `specs/001-fix-wise-pdf-date-format/quickstart.md` ("Reproduce") against the inbox PDF and record that `WiseStatementAdapter().parse(...)` returns 0 (no code change).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Provide the European-ordering test fixture that every US1 test depends on.

**⚠️ CRITICAL**: US1 tests cannot be written/run until the fixture exists.

- [X] T002 Add the `Day Month Year` fixture `tests/fixtures/wise/may_2026.pdf` by copying the real inbox statement (`~/.finance/inbox/df9e4c5357aa367957a71f9e5390f98b38bba4046139b698bf2111f776cc604c.pdf`), mirroring the existing `tests/fixtures/wise/april_2026.pdf` pattern (per research.md R4). Verify it extracts text containing dates like `31 May 2026`.

**Checkpoint**: Fixture in place — US1 work can begin.

---

## Phase 3: User Story 1 - Import a statement regardless of the date locale Wise used (Priority: P1) 🎯 MVP

**Goal**: The Wise adapter parses transactions whether dates are written
`Month Day, Year` (`April 30, 2026`) or `Day Month Year` (`31 May 2026`),
producing one draft per line item in either ordering.

**Independent Test**: Run `uv run pytest tests/unit/test_wise_adapter.py -q` — the
parametrized parse test passes for both `april_2026.pdf` (month 4) and
`may_2026.pdf` (month 5), each yielding a non-zero transaction count with
correct dates/amounts/payees.

### Tests for User Story 1 (write first, ensure they FAIL) ⚠️

- [X] T003 [US1] In `tests/unit/test_wise_adapter.py`, refactor `test_parse_clean_fixture_yields_transactions` into a fixture-parametrized test over `[(april_2026.pdf, 2026, 4), (may_2026.pdf, 2026, 5)]`, asserting `len(parsed) > 20`, EUR currency, non-zero amounts, non-empty payees, and `posted_date.year/month` matching the parameter. (Same file as T004/T005 — keep sequential.)
- [X] T004 [US1] In `tests/unit/test_wise_adapter.py`, add `test_parse_eu_ordering_spot_check` asserting a known May line — the `31 May 2026` Claude.ai subscription → `amount_minor == -2142`, EUR, `posted_date == date(2026, 5, 31)`, payee contains `Claude.ai`.
- [X] T005 [US1] In `tests/unit/test_wise_adapter.py`, add `test_parse_eu_single_digit_day` (GIVEN/WHEN/THEN) asserting a `5 May 2026`-style date resolves to `posted_date.day == 5` (drive from a real `may_2026.pdf` line that has a single-digit day, or assert via the lowest-day May transaction).

### Implementation for User Story 1

- [X] T006 [US1] In `src/finance/ingestion/wise_pdf.py`, add the EU date pattern `_DATE_LINE_EU_RE = ^(?P<day>\d{1,2})\s+(?P<month>{_MONTH_ALT})\s+(?P<year>\d{4})\b` and make the existing US pattern's comma optional (`,?`) per FR-002 / research.md R1.
- [X] T007 [US1] In `src/finance/ingestion/wise_pdf.py`, add helpers `_match_date(line) -> re.Match | None` (tries US then EU pattern) and `_date_from_match(m) -> date` (single place that builds `date(year, month, day)` from either ordering's named groups).
- [X] T008 [US1] In `src/finance/ingestion/wise_pdf.py`, replace the block-flush check (`_DATE_LINE_RE.match(ln)` in `parse`) and the date extraction in `_make_tx` to use `_match_date` / `_date_from_match`, ensuring `memo = last[m.end():].strip()` still works for both orderings.

**Checkpoint**: US1 tests (T003–T005) pass; `may_2026.pdf` parses to a non-zero, correct transaction set; April behaviour unchanged.

---

## Phase 4: User Story 2 - Surface a clear failure instead of silently producing nothing (Priority: P2)

**Goal**: A recognised Wise statement (valid currency header) that yields zero
transactions raises `AdapterParseError` instead of returning `[]`, so the
Telegram bot and CLI report a failure rather than "created 0 drafts".

**Independent Test**: Feed the adapter a Wise-headed but transaction-free /
unparseable body and assert it raises `AdapterParseError`; confirm the existing
April and May fixtures still parse (the guard only trips on genuinely empty results).

### Tests for User Story 2 (write first, ensure it FAILS) ⚠️

- [X] T009 [P] [US2] Add `test_parse_recognised_statement_with_no_transactions_raises` in `tests/unit/test_wise_adapter.py` (GIVEN a Wise-headed PDF/body with the column header but no transaction lines, WHEN parsed, THEN `AdapterParseError` is raised mentioning `wise-pdf`). Build the input as a minimal fixture or by trimming an extracted body; keep it independent of US1 assertions.

### Implementation for User Story 2

- [X] T010 [US2] In `src/finance/ingestion/wise_pdf.py`, after the parse loop in `parse`, raise `AdapterParseError(self.id, "recognised a Wise statement header but parsed 0 transactions; the statement layout may be unsupported")` when `results` is empty (per FR-006 / research.md R3). No caller changes — bot `handlers.py:309` and CLI `_runtime.py:53` already surface it.

**Checkpoint**: US1 AND US2 both pass; silent empty success is no longer possible for Wise-shaped files.

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: End-to-end confidence and repo hygiene.

- [X] T011 [P] Add/extend an integration test in `tests/integration/test_ingestion.py` that imports `tests/fixtures/wise/may_2026.pdf` through `import_artifact` into a EUR account and asserts `draft_count > 0` (covers SC-001 / SC-005, the original GUI report).
- [X] T012 [P] Run `make lint` and `make typecheck` (ruff + mypy) and fix any findings introduced in `src/finance/ingestion/wise_pdf.py`.
- [X] T013 Run the full suite `make test` and the `quickstart.md` "Confirm the fix" + acceptance-mapping steps; confirm April drafts are byte-identical to pre-change (FR-008 / SC-003) and May now yields drafts.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Setup. T002 (fixture) **blocks all US1 tests**.
- **User Story 1 (Phase 3)**: Depends on Phase 2 (needs the fixture). MVP.
- **User Story 2 (Phase 4)**: Depends on Phase 2; logically independent of US1 but **edits the same file** (`wise_pdf.py`), so sequence T006–T008 before T010 to avoid edit conflicts.
- **Polish (Phase 5)**: Depends on US1 (T011 needs the parsing fix) and ideally US2.

### User Story Dependencies

- **US1 (P1)**: The fix. Independently testable via the unit fixture parametrization.
- **US2 (P2)**: Hardening. Independently testable via the empty-statement test. Shares `wise_pdf.py` with US1 → not parallel at the file level.

### Within Each User Story

- Tests written before implementation (T003–T005 before T006–T008; T009 before T010).
- In `wise_pdf.py`: patterns (T006) → helpers (T007) → call-site wiring (T008) → fail-loud guard (T010).

### Parallel Opportunities

- T011 and T012 are `[P]` (different files / read-only tooling) once US1 is implemented.
- T009 is `[P]` relative to US1 implementation only if authored against a separate fixture; since it shares `test_wise_adapter.py` with T003–T005, treat the test-file edits as sequential in practice.
- Note: the three US1 unit-test tasks (T003–T005) all edit `test_wise_adapter.py`, so despite being one story they are **not** mutually `[P]`.

---

## Parallel Example: Polish phase

```bash
# After US1 implementation lands, run in parallel:
Task: "Integration test importing may_2026.pdf in tests/integration/test_ingestion.py"  # T011
Task: "Run make lint && make typecheck"                                                  # T012
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1: Setup (T001 — capture the failing baseline).
2. Phase 2: Foundational (T002 — add the May fixture).
3. Phase 3: User Story 1 (T003–T008 — tests then the locale-tolerant matcher).
4. **STOP and VALIDATE**: `may_2026.pdf` parses; April unchanged. This alone
   resolves the reported "0 drafts" bug and is shippable.

### Incremental Delivery

1. Setup + Foundational → fixture ready.
2. US1 → reported bug fixed (MVP, shippable on its own).
3. US2 → silent-empty failures become loud errors.
4. Polish → e2e integration + lint/type/full-suite green.

### Notes

- `[P]` = different files, no dependencies.
- US1 and US2 both edit `src/finance/ingestion/wise_pdf.py`; do US1 first.
- Verify each new test FAILS before writing the implementation it covers.
- Commit after each logical group; land as `fix(ingestion): …` per AGENTS.md.
- Branch-naming reconciliation tracked in research.md R6 (handle at PR time).
