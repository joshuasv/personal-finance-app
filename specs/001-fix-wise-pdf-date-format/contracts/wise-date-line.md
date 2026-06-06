# Contract: Wise statement date-line recognition

The Wise PDF adapter exposes no public API beyond the `InstitutionAdapter`
protocol (`parse(path) -> Iterable[ParsedTransaction]`). The contract that
changes here is the **internal recognition contract** for what counts as a
transaction date line and what the adapter guarantees about its output. It is
documented as a contract because the tests assert against it directly.

## Input

A line of text extracted from a Wise statement body (one of `lines[start:]`).

## Recognition contract

A line is a **transaction date line** if and only if it begins with one of:

| Form              | Regex intent                                         | Accept examples            | Reject examples                 |
|-------------------|------------------------------------------------------|----------------------------|---------------------------------|
| US: `Month D[,] Y`| `^<Month>\s+\d{1,2},?\s+\d{4}\b`                      | `April 30, 2026`, `April 5 2026` | `30 April 2026`, `Apr 30, 2026` |
| EU: `D Month Y`   | `^\d{1,2}\s+<Month>\s+\d{4}\b`                        | `31 May 2026`, `5 May 2026` | `2026 May 31`, `31/05/2026`     |

Where `<Month>` is an English full month name (`January`…`December`).

- Leading zero on the day is optional in both forms (`5` ≡ `05`).
- The comma is optional in the US form.
- Matching is anchored at line start (`^`) and bounded by `\b` after the year,
  so trailing memo text (`… Card ending in 8273 …`) does not affect the match
  and remains available as `memo`.
- The two forms are mutually exclusive (month-word-first vs digit-first), so
  recognition is independent of evaluation order.

## Output guarantees

For any statement whose currency header is recognised:

1. **Completeness**: every visible transaction line item yields exactly one
   `ParsedTransaction` (modulo the existing in-batch dedup in the pipeline).
2. **Date fidelity**: `posted_date == date(year, month, day)` as printed on the
   statement, for either ordering.
3. **Non-silence**: if recognition yields **zero** transactions, `parse` MUST
   raise `AdapterParseError` (never return an empty iterable).
4. **Regression**: for the US-ordering fixture, output is identical to
   pre-change behaviour (same count, same field values).

## Consumer-side contract (already satisfied, no change)

- Telegram (`handlers.py:309`): `AdapterParseError` → user message
  "Import failed via wise-pdf: …".
- CLI (`_runtime.py:53`): `AdapterParseError` → clean `fail()` exit, no
  traceback.

## Test obligations

- Parametrized parse test over `april_2026.pdf` (US, month 4) and
  `may_2026.pdf` (EU, month 5): both non-empty, correct `(year, month)`.
- EU value spot-check: a known `31 May 2026` line maps to the right
  `amount_minor` / `payee` / `posted_date`.
- Single-digit-day EU date parses to the correct day.
- Fail-loud: a Wise-headed but unparseable body raises `AdapterParseError`.
- US regression: existing April assertions remain green unchanged.
