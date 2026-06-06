# Phase 1 Data Model: Locale-tolerant Wise date parsing

This change introduces **no new persisted entities** and **no schema changes**.
The "data" here is the in-memory parse representation and the transient match
structure used while reading a statement. Documented for completeness.

## Entities

### ParsedTransaction (existing — unchanged)

Defined in `src/finance/ingestion/protocols.py`. One transaction extracted from
a statement; becomes one `DraftTransaction` row downstream.

| Field          | Type        | Notes                                              |
|----------------|-------------|----------------------------------------------------|
| `posted_date`  | `date`      | **Affected**: now resolved correctly from either date ordering |
| `amount_minor` | `int`       | Signed minor units; unchanged                      |
| `currency`     | `str`       | ISO 4217 from the `<CCY> statement` header; unchanged |
| `payee`        | `str`       | Description head + wrapped continuation lines; unchanged |
| `memo`         | `str | None`| Trailing text after the date on the date line; unchanged |

**Invariant strengthened**: `posted_date` MUST equal the calendar date a human
reads on the statement regardless of the locale ordering used (FR-003).

### Statement date line (transient parse concept — generalised)

Not a stored type — the line that terminates a transaction block. Previously
recognised in exactly one shape; now in a tolerant family:

| Variant | Example         | Pattern intent                                  |
|---------|-----------------|-------------------------------------------------|
| US      | `April 30, 2026`| `Month Day[,] Year` — comma optional            |
| US (1-digit day) | `April 5, 2026` | day `\d{1,2}`                          |
| EU      | `31 May 2026`   | `Day Month Year`                                |
| EU (1-digit day) | `5 May 2026`    | day `\d{1,2}`, no leading zero         |

**Resolution rule**: both variants yield `(year:int, month:int, day:int)` via a
single shared converter, so the rest of the parser is ordering-agnostic. Month
names are English `January`…`December` (existing `_MONTHS` map, unchanged).

## State / flow (unchanged shape, generalised trigger)

The block-accumulation state machine is unchanged:

```
accumulate lines into `block`
  └─ when a line matches the (now locale-tolerant) date matcher
     AND block has ≥ 2 lines  → flush block into a ParsedTransaction, reset
end of body (trailer prefix)  → stop
after loop: if zero transactions → raise AdapterParseError   ← NEW
```

The only behavioural deltas:
1. The "line matches a date" predicate now accepts both orderings.
2. A new terminal guard converts a silent empty result into a raised error.

## Validation rules (from requirements)

- A date line MUST resolve to a valid `datetime.date`; an impossible date
  (e.g. day 31 in a 30-day month) surfaces as the existing `ValueError` from
  `date(...)`, wrapped as `AdapterParseError` (no new handling needed — matches
  current behaviour for malformed dates).
- A recognised Wise statement (valid currency header) MUST NOT produce zero
  transactions silently (FR-006).
