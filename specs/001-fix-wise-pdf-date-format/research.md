# Phase 0 Research: Locale-tolerant Wise date parsing

All unknowns from the Technical Context are resolved below. Each entry follows
Decision / Rationale / Alternatives considered.

## R1. How to match both date orderings without breaking the existing one

**Decision**: Introduce a single helper `_match_date(line: str) -> re.Match | None`
backed by **two compiled patterns tried in order** — the existing US pattern
and a new EU pattern — rather than one mega-regex. Both the block-flush check
and `_make_tx` call this helper.

- US (unchanged behaviour): `^(?P<month>{MONTHS})\s+(?P<day>\d{1,2}),?\s+(?P<year>\d{4})\b`
  (comma made optional via `,?` for tolerance — FR-002).
- EU (new): `^(?P<day>\d{1,2})\s+(?P<month>{MONTHS})\s+(?P<year>\d{4})\b`

The helper returns the match; callers read `group("year"|"month"|"day")`. A
tiny `_date_from_match(m) -> date` builds the `datetime.date`, shared by both
orderings, so day/month/year extraction lives in exactly one place.

**Rationale**: Python's stdlib `re` **forbids duplicate group names** within a
single pattern, so a single alternation `(A)|(B)` cannot reuse
`(?P<day>…)`/`(?P<month>…)` in both branches. Two patterns keep named groups
clean, keep the US path byte-identical (regression safety, FR-008), and read
clearly. The matcher is order-independent because the two patterns are mutually
exclusive: a US line starts with a month word, an EU line starts with a digit.

**Alternatives considered**:
- *One regex with numbered groups + post-processing* — works but obscures which
  ordering matched and is harder to read; rejected for clarity.
- *`dateutil.parser` / `datetime.strptime` sweep* — pulls in ambiguity
  (`05 06 2026`?) and, for `dateutil`, a new dependency. The statement always
  carries an explicit English month name, so a targeted regex is both safer and
  dependency-free. Rejected.
- *`regex` third-party module* (allows duplicate group names) — new dependency
  for no real gain. Rejected.

## R2. Will the statement period / "Generated on" lines be misread as transactions?

**Decision**: No change needed; they remain excluded **positionally**.

**Rationale**: The parser only scans `lines[start:]`, where `start` is the line
after the `Description Incoming Outgoing Amount` column header. The period line
(`1 May 2026 [GMT+02:00] - 31 May 2026 …`) and `Generated on: 6 June 2026` both
sit in the page-1 header **above** that column header, so they are never fed to
the date matcher. Verified against both the April (US) and May (EU) extracted
text. This satisfies FR-005 for both orderings without new guards.

**Alternatives considered**: Adding an explicit "skip lines containing
`GMT`/`Generated on`" filter — unnecessary belt-and-suspenders; rejected to
avoid dead code. (Noted as a fallback if a future layout moves these lines.)

## R3. Fail-loud on zero transactions

**Decision**: After the parse loop, if `results` is empty, raise
`AdapterParseError(self.id, "...recognised a Wise statement header but parsed 0 "
"transactions; the statement layout may be unsupported")`. The currency-header
check already guarantees we only reach this point for Wise-shaped files.

**Rationale**: This is the deeper defect (FR-006): a recognised statement that
yields nothing should not masquerade as success. Both surfaces already render
`AdapterParseError`:
- Telegram: `handlers.py:309` `except Exception as exc:` → "Import failed via
  wise-pdf: …".
- CLI: `_runtime.py:53` `except (DomainError, AdapterParseError)` → clean `fail()`.

So **no caller changes** are required — raising is sufficient end-to-end.

**Alternatives considered**:
- *Return `[]` and let callers warn* — that is exactly today's silent-failure
  behaviour; rejected.
- *Distinguish "empty statement period" from "unparseable"* — Wise does not
  emit a reliable "no transactions" marker we can key on, and a genuinely
  empty month is rare. Per spec Assumptions we accept erroring in that edge
  case ("fail loud over silent data loss"). Documented, not implemented.

## R4. Test fixture for the European ordering (PII consideration)

**Decision**: Add `tests/fixtures/wise/may_2026.pdf` — the real `Day Month Year`
statement (the file already sitting in the local inbox,
`~/.finance/inbox/df9e4c…​.pdf`).

**Rationale**: This mirrors the existing pattern exactly — `april_2026.pdf` is
itself a real statement carrying the same account holder's name, IBAN, and
address. Using the genuine file gives the highest-fidelity regression guard
(true pdfplumber text extraction, real wrapping like the `COM` / `Amsterdam`
continuation lines). Consistency with the established fixture beats inventing a
synthetic PDF whose extracted-text layout might not match Wise's real output.

**PII note**: The repo already commits this person's real statement data as a
test fixture, so adding a second month does not change the project's existing
privacy posture. If the maintainer later wants the fixtures anonymised, that is
a separate, broader change applying equally to `april_2026.pdf`. Flagged for
visibility, not blocking.

**Alternatives considered**:
- *Generate a synthetic PDF with reportlab* — no PII, deterministic, but the
  extracted-text layout is hand-rolled and may drift from Wise's actual output,
  weakening the regression value of the test. Rejected for now; revisit only if
  anonymisation becomes a requirement.

## R5. Test shape (AGENTS.md "tests are the review artifact")

**Decision**: Refactor `test_wise_adapter.py` so the core correctness assertions
are **parametrized over both fixtures** (`april_2026.pdf` → month 4 / 2026,
`may_2026.pdf` → month 5 / 2026), each tagged with its expected `(year, month)`
and minimum transaction count. Add a focused EU-specific test asserting a known
line (e.g. the `31 May 2026` Claude.ai `-21.42` → `-2142` minor) and an
edge-case test for a single-digit EU day. Add a fail-loud test feeding a
header-only / unparseable Wise-shaped document and asserting `AdapterParseError`.

**Rationale**: Parametrization makes the spec's "both orderings held to the same
bar" (FR-007, SC-002) literally visible in the test report. GIVEN/WHEN/THEN
naming per AGENTS.md.

**Alternatives considered**: Copy-pasting the April assertions into a separate
May test — duplicative and lets the two drift; rejected in favour of
parametrization.

## R6. Branch naming reconciliation (process note)

**Observation**: AGENTS.md prescribes `feat/<slug>` / `fix/<slug>` branches off
`dev`. The speckit `before_specify` hook created `001-fix-wise-pdf-date-format`
off the current branch instead. This is a process mismatch, not a code issue.

**Decision**: Proceed on the speckit branch for the spec artifacts; at landing
time, rename/retarget to a conventional `fix/wise-pdf-date-format` branch
targeting `dev` (or let `/ship` handle it) so the merge follows AGENTS.md. No
action needed during implementation. Flagged so it is not forgotten at PR time.
