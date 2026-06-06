# Quickstart: verifying the locale-tolerant date fix

How to reproduce the bug and confirm the fix, by hand and via tests.

## Reproduce (before the fix)

```bash
# Parse the real European-ordering statement that produced 0 drafts.
uv run python - <<'PY'
from pathlib import Path
from finance.ingestion.wise_pdf import WiseStatementAdapter
p = Path.home() / ".finance/inbox/df9e4c5357aa367957a71f9e5390f98b38bba4046139b698bf2111f776cc604c.pdf"
print("parsed:", len(list(WiseStatementAdapter().parse(p))))   # -> 0  (the bug)
PY
```

## Confirm the fix

```bash
# Same call after the change should report a non-zero count (~50+ for May).
uv run python - <<'PY'
from pathlib import Path
from finance.ingestion.wise_pdf import WiseStatementAdapter
p = Path("tests/fixtures/wise/may_2026.pdf")
txs = list(WiseStatementAdapter().parse(p))
print("parsed:", len(txs))
assert txs, "EU statement still parses 0 — fix not applied"
print("sample:", txs[0].posted_date, txs[0].amount_minor, txs[0].payee)
PY
```

## End-to-end (GUI path, mirrors the original report)

```bash
uv run finance serve --with-ui      # or: make run-all
# Re-send the May statement to the Telegram bot, OR:
uv run finance import wise-pdf tests/fixtures/wise/may_2026.pdf --account "Wise EUR"
uv run finance draft list           # drafts now appear (previously empty)
```

Expected bot reply after the fix: `Batch #N: created <count> drafts.` instead
of `created 0 drafts`. For an unparseable statement-shaped file, expect
`Import failed via wise-pdf: …` rather than a silent zero.

## Run the tests

```bash
uv run pytest tests/unit/test_wise_adapter.py tests/integration/test_ingestion.py -q
# or the whole suite:
make test
```

The parametrized parse test now exercises both `april_2026.pdf` (US ordering)
and `may_2026.pdf` (EU ordering); the fail-loud test asserts `AdapterParseError`
on a Wise-headed but unparseable body.

## Acceptance mapping

| Spec item        | Verified by                                              |
|------------------|---------------------------------------------------------|
| FR-001 / SC-002  | parametrized parse test (both orderings non-empty)      |
| FR-002 / edge    | single-digit-day EU date test                           |
| FR-003           | EU value spot-check (date/amount/payee)                 |
| FR-005           | period / "Generated on" lines excluded (positional)     |
| FR-006 / SC-004  | fail-loud `AdapterParseError` test                      |
| FR-008 / SC-003  | unchanged April assertions stay green                   |
| SC-001 / SC-005  | end-to-end import yields drafts in GUI/CLI              |
