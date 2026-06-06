# Implementation Plan: Parse Wise PDF dates in a general, locale-tolerant form

**Branch**: `001-fix-wise-pdf-date-format` | **Date**: 2026-06-06 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/001-fix-wise-pdf-date-format/spec.md`

## Summary

The Wise PDF adapter recognises transaction date lines with a single regex
that only accepts the US ordering `Month Day, Year` (e.g. `April 30, 2026`).
When a statement is exported with a different locale selected in Wise's GUI —
e.g. the UK ordering `Day Month Year` (`31 May 2026`) — no transaction block
is ever completed, the parser returns `[]`, and the importer writes **0
drafts silently**.

The fix is localized to `src/finance/ingestion/wise_pdf.py`: replace the
single-ordering date pattern with a small **locale-tolerant date matcher** that
accepts both observed orderings (plus benign leading-zero / comma variation),
and make the adapter **fail loudly** (raise `AdapterParseError`) when it
recognises a Wise statement header but extracts zero transactions, so a future
unknown layout can never again be swallowed as a silent empty success. A new
`Day Month Year` PDF fixture and tests lock in both orderings.

No database, API, model, bot, or CLI changes are required: both the Telegram
handler (`handlers.py:309`) and the CLI runtime (`_runtime.py:53`) already
surface `AdapterParseError` to the user.

## Technical Context

**Language/Version**: Python 3.12 (`from __future__ import annotations` in use)

**Primary Dependencies**: `pdfplumber` (text extraction), stdlib `re` and
`datetime`; `pytest` + `hypothesis` for tests

**Storage**: N/A for this change (drafts persist via existing SQLAlchemy
pipeline; untouched)

**Testing**: `pytest` (unit + integration). Fixtures are checked-in PDFs under
`tests/fixtures/wise/`

**Target Platform**: Local-first CLI / FastAPI / Telegram bot on Linux

**Project Type**: Single Python package (`src/finance/...`) — Option 1

**Performance Goals**: N/A — statement parsing is interactive, one file at a
time; no throughput target

**Constraints**: Must not regress the existing `april_2026.pdf` fixture
(byte-for-byte same drafts). Pure-stdlib date matching (no new dependency).

**Scale/Scope**: ~1 file changed (`wise_pdf.py`), 1 new fixture, ~3–4 new
tests. English-month statements only (per spec Assumptions).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

The project constitution at `.specify/memory/constitution.md` is an **unfilled
template** (placeholder tokens only), so there are no ratified gates to
evaluate. In its place this plan is held to the project's real, written
conventions in `AGENTS.md`:

- **Tests are the review artifact** — GIVEN/WHEN/THEN structure, visible in
  names/docstrings; reads top-to-bottom as a spec. ✅ planned (see quickstart).
- **Prefer integration over heavy mocking** — the new test parses a real PDF
  fixture end-to-end, not a mocked `pdfplumber`. ✅
- **Conventional Commits** — change will land as `fix(ingestion): ...`. ✅
- **Branch off `dev`, target `dev`** — note: the speckit hook created
  `001-fix-wise-pdf-date-format` off the current branch; see
  [research.md](./research.md) "Branch naming reconciliation". ⚠️ tracked.

No violations. No entries needed in Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/001-fix-wise-pdf-date-format/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── wise-date-line.md  # Parser date-line contract
├── checklists/
│   └── requirements.md  # From /speckit-specify
└── tasks.md             # /speckit-tasks output (NOT created here)
```

### Source Code (repository root)

```text
src/finance/ingestion/
├── wise_pdf.py          # CHANGED: locale-tolerant date matcher + fail-loud-on-empty
└── protocols.py         # unchanged (AdapterParseError already defined)

tests/
├── fixtures/wise/
│   ├── april_2026.pdf   # existing US-ordering fixture (regression guard)
│   └── may_2026.pdf     # NEW: Day-Month-Year ordering fixture
├── unit/
│   └── test_wise_adapter.py  # CHANGED: parametrize over both fixtures + edge cases
└── integration/
    └── test_ingestion.py     # CHANGED (if needed): end-to-end May import yields drafts
```

**Structure Decision**: Single-project layout (Option 1). The entire change is
contained to the ingestion adapter and its tests; no new modules, packages, or
cross-cutting wiring.

## Complexity Tracking

> No constitution violations. Section intentionally empty.
