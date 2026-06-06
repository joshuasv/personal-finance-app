# Feature Specification: Parse Wise PDF dates in a general, locale-tolerant form

**Feature Branch**: `001-fix-wise-pdf-date-format`

**Created**: 2026-06-06

**Status**: Draft

**Input**: User description: "there is a bug somewhere, just uploaded the PDF statement for this month but generated 0 drafts; please investigate why; capture it in a test and fix"

## Context & Root Cause *(investigation summary)*

A user sent a recent Wise statement to the Telegram bot. The file downloaded
successfully (HTTP 200) and was stored in the inbox, but **0 drafts** were
created — the import silently produced nothing.

Investigation of the actual failing file in the inbox showed the cause: Wise
emits statement dates in a **different locale format** than the one the
adapter recognises.

- The known-good April statement uses **US style**: `April 30, 2026`
  (`Month Day, Year`, with a comma).
- The newly uploaded statement (period "1 May 2026 – 31 May 2026", generated
  6 June 2026) uses **European/UK style**: `31 May 2026`
  (`Day Month Year`, no comma).

The format is **not a property of the user's account** — it is chosen from a
locale/region dropdown in the Wise statement-export GUI at generation time.
The original adapter was developed exclusively against US-style exports; the
first time a statement was generated with a different (UK) locale selected, it
failed. Any of Wise's offered locales could be selected on any future export.

The adapter identifies the end of each transaction block by matching a date
line. Its date pattern only accepts the US style, so when the statement uses
any other style **no transaction block is ever completed**, the parser returns
an empty list, and the importer writes zero drafts. Running the adapter
against the real inbox file confirmed `0 transactions parsed`.

This is a user-facing data-loss-of-visibility bug: a perfectly valid statement
is silently ignored, leaving the user's ledger missing an entire month. The
fix is therefore not "add the one UK variant" but "**parse dates in a general,
locale-tolerant form**" so the surface no longer depends on which option the
user happened to pick in the export dropdown.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Import a statement regardless of the date locale Wise used (Priority: P1)

A user uploads a Wise statement without knowing or caring which locale was
selected when it was exported. Whether the transaction dates read
`April 30, 2026` (`Month Day, Year`) or `31 May 2026` (`Day Month Year`), the
system parses every transaction and creates one draft per transaction. The
import succeeds the same way for both, so the choice in Wise's export dropdown
no longer determines whether the upload works.

**Why this priority**: This is the reported defect, generalised. Without it, an
upload's success depends on an arbitrary GUI choice the user makes outside this
app, and a "wrong" choice silently produces nothing with no indication of
failure. Accepting dates in a general form is the minimum viable fix.

**Independent Test**: Run the Wise adapter against statement fixtures in each
supported date ordering and assert each returns the full set of transactions
(non-zero, matching the statement's visible line items), with correct dates,
amounts, payees, and currency — driven from a single shared assertion so both
orderings are held to the same bar.

**Acceptance Scenarios**:

1. **Given** a Wise statement whose transaction dates read `31 May 2026` (`Day Month Year`), **When** it is imported, **Then** one draft is created per transaction line with the correct posted date (year/month/day), amount, payee, and currency.
2. **Given** a Wise statement whose transaction dates read `April 30, 2026` (`Month Day, Year`), **When** it is imported, **Then** it parses correctly with no change from prior behaviour (no regression).
3. **Given** either statement, **When** parsing finishes, **Then** the number of drafts created equals the number of transaction line items shown in the statement (greater than zero).
4. **Given** a date with no leading zero on the day (e.g. `5 May 2026`) or a single-digit US day (e.g. `April 5, 2026`), **When** it is imported, **Then** the transaction is parsed with the correct day.

---

### User Story 2 - Surface a clear failure instead of silently producing nothing (Priority: P2)

When a statement is recognised as a Wise statement (correct header) but the
adapter extracts **zero** transactions, the system reports this as an error
rather than completing "successfully" with an empty result, so the user knows
the upload needs attention.

**Why this priority**: The deeper failure mode here was not the date format
alone — it was that an unrecognised layout produced a *silent* empty success.
Even after the date fix, a future layout change should fail loudly rather than
swallow a month of data. Important, but secondary to restoring the happy path.

**Independent Test**: Feed the adapter a Wise-looking document whose body the
parser cannot interpret and assert it raises a parse error (surfaced to the
Telegram user / CLI) instead of returning an empty list and reporting success.

**Acceptance Scenarios**:

1. **Given** a document with a valid `<CCY> statement` header but no parseable transaction lines, **When** it is imported, **Then** the system raises a parse error that is reported to the user, and no empty "0 drafts" success is shown as if normal.
2. **Given** the Telegram upload path, **When** parsing yields zero transactions for a statement-shaped file, **Then** the bot replies with a message indicating the statement could not be parsed.

---

### Edge Cases

- **Single-digit days**: `5 May 2026` and `April 5, 2026` (no leading zero) must parse, as must `05 May 2026`.
- **Either ordering per file**: a statement uses one ordering throughout; the parser must accept a file that contains *only* the US ordering or *only* the European ordering — it must not require either specific one to be present.
- **Period/header lines**: the statement period line ("1 May 2026 … - 31 May 2026 …") and "Generated on: 6 June 2026" line also use the new format; these must continue to be ignored (not mistaken for transactions), as they already are.
- **Multi-line (wrapped) descriptions**: transactions whose description wraps across lines (e.g. the `COM` / `Amsterdam` continuation lines seen in the fixture) must still be attached to the correct transaction.
- **Genuinely empty statement**: a valid statement period with no transactions at all — distinguishing "no transactions this period" from "parser failed to read transactions" (see User Story 2). Assumption documented below.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The Wise statement adapter MUST parse transaction dates in a general, locale-tolerant form rather than a single hard-coded ordering. It MUST accept, at minimum, both orderings Wise is known to emit: `Month Day, Year` (e.g. `April 30, 2026`) and `Day Month Year` (e.g. `31 May 2026`).
- **FR-002**: Date parsing MUST tolerate benign formatting variation within those orderings: the day with or without a leading zero (`5` and `05`), and the optional trailing comma after the day in the US ordering.
- **FR-003**: The adapter MUST resolve each accepted date to the correct calendar day (year, month, day) so that drafts carry the same posted date a human reads on the statement, irrespective of which ordering was used.
- **FR-004**: For any supported statement, the adapter MUST produce exactly one transaction per statement line item, with the correct posted date, amount (sign preserved), payee, currency, and memo — including transactions whose description wraps across lines.
- **FR-005**: Lines that contain dates but are not transactions (the statement period line and the "Generated on" line) MUST continue to be ignored under every supported date ordering, never mistaken for transaction date lines.
- **FR-006**: The system MUST NOT report an import as successful with zero drafts when the source is a recognised Wise statement whose transactions could not be parsed; it MUST instead surface a parse error to the originating surface (Telegram bot and CLI).
- **FR-007**: A regression test fixture representing a `Day Month Year` statement MUST be added to the test suite alongside the existing `Month Day, Year` fixture, with both held to the same correctness assertions (non-zero, correct transaction count and field values).
- **FR-008**: The fix MUST NOT change drafts already produced for previously supported statements (no re-parsing differences for the existing April fixture).

### Key Entities *(include if feature involves data)*

- **Parsed Transaction**: one transaction extracted from a statement — posted date, amount, currency, payee, memo. The unit that becomes a draft.
- **Wise Statement (source artifact)**: the uploaded PDF; carries a currency header, a statement period, and a list of transaction blocks each terminated by a date line in one of the supported locale formats.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Importing the previously failing statement produces the same number of drafts as there are transaction line items in the statement (zero failures, zero silent empties).
- **SC-002**: 100% of transactions are captured with correct date, amount, and payee in a statement of *either* supported date ordering, exercised by fixtures for both.
- **SC-003**: The existing US-format statement continues to parse with no change in the number or content of drafts (no regression).
- **SC-004**: A statement-shaped file that the parser cannot interpret results in a visible error to the user in 100% of cases, never a silent "0 drafts" success.
- **SC-005**: A user re-uploading the affected statement after the fix sees the month's transactions appear as drafts in the GUI/CLI on the first attempt.

## Assumptions

- "General form" is scoped to the variants Wise's export dropdown actually produces with **English month names**: the two observed orderings (`Month Day, Year` and `Day Month Year`) plus benign leading-zero/comma variation. Fully numeric orderings (e.g. `YYYY-MM-DD` or `DD/MM/YYYY`) and non-English month names are *not* required now, because they have not been observed from Wise — but FR-001 is written as "locale-tolerant" so adding one later is a localized change, not a redesign. The user picking a different dropdown option should not break import within this English-month family.
- The date ordering is selected per-export in the Wise GUI, not fixed per account, so a single user may upload statements in different orderings over time; the adapter must handle them interchangeably without configuration.
- The "recognised Wise statement but zero transactions" error (User Story 2 / FR-004) treats a genuinely transaction-free statement period as an unlikely-enough case that erroring is acceptable; if a real empty-period statement surfaces, it can be whitelisted later. This is a deliberate "fail loud" choice over silent data loss.
- The original failing PDF remains available in the local inbox and can be used to derive a sanitised test fixture; the regression fixture will mirror its layout (it may reuse/anonymise that file).
- No database, API schema, or account model changes are required — the fix is contained to the ingestion adapter and its error surfacing.
