"""Wise PDF statement adapter.

Parses Wise monthly statement PDFs into `ParsedTransaction` records. The
adapter is intentionally narrow: it only handles the layout shipped by
`tests/fixtures/wise/`. New layouts are accommodated by adding fixtures and
extending this module — `core` does not change.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import date
from pathlib import Path

import pdfplumber

from finance.ingestion.protocols import AdapterParseError, ParsedTransaction

_MONTHS = {
    "January": 1,
    "February": 2,
    "March": 3,
    "April": 4,
    "May": 5,
    "June": 6,
    "July": 7,
    "August": 8,
    "September": 9,
    "October": 10,
    "November": 11,
    "December": 12,
}
_MONTH_ALT = "|".join(_MONTHS)

# A line ending with "<amount> <balance>" — both decimals, amount may be signed.
_AMOUNT_BALANCE_RE = re.compile(
    r"\s(?P<amount>-?[\d,]+\.\d+)\s+(?P<balance>-?[\d,]+\.\d+)\s*$"
)
# Date line, e.g. "April 30, 2026 Card ending in 8273 ..."
_DATE_LINE_RE = re.compile(
    rf"^(?P<month>{_MONTH_ALT})\s+(?P<day>\d{{1,2}}),\s+(?P<year>\d{{4}})\b"
)
# Currency declaration in the header: "EUR statement" / "GBP statement"
_CURRENCY_HEADER_RE = re.compile(r"(?m)^([A-Z]{3})\s+statement\b")
# Page footer: "ref:<uuid>  <n> / <total>"
_PAGE_FOOTER_RE = re.compile(r"^ref:[a-f0-9-]+\s+\d+\s*/\s*\d+\s*$")
# Disclaimer / footer lines that mark end-of-content on the last page
_TRAILER_PREFIXES = (
    "Wise is the trading name",
    "Need help?",
)


def _parse_minor(text: str, decimals: int = 2) -> int:
    sign = -1 if text.startswith("-") else 1
    body = text.lstrip("+-").replace(",", "")
    if "." in body:
        major, frac = body.split(".", 1)
    else:
        major, frac = body, ""
    frac = (frac + "0" * decimals)[:decimals]
    return sign * (int(major) * 10**decimals + int(frac))


class WiseStatementAdapter:
    """Adapter for Wise monthly account statements (PDF)."""

    id = "wise-pdf"
    display_name = "Wise (PDF statement)"
    source_artifact_type = "application/pdf"

    def parse(self, path: Path) -> Iterable[ParsedTransaction]:
        try:
            with pdfplumber.open(path) as pdf:
                pages = [(i + 1, p.extract_text() or "") for i, p in enumerate(pdf.pages)]
        except AdapterParseError:
            raise
        except Exception as exc:
            raise AdapterParseError(self.id, f"could not open PDF: {exc}") from exc

        if not pages:
            raise AdapterParseError(self.id, "PDF has no pages")

        m = _CURRENCY_HEADER_RE.search(pages[0][1])
        if m is None:
            raise AdapterParseError(
                self.id,
                "missing '<CCY> statement' header on page 1; this does not "
                "look like a Wise statement",
                page=1,
            )
        currency = m.group(1)

        lines: list[tuple[int, str]] = []
        for pno, text in pages:
            for raw in text.splitlines():
                ln = raw.strip()
                if not ln or _PAGE_FOOTER_RE.match(ln):
                    continue
                lines.append((pno, ln))

        # Body starts after the column header on page 1.
        start: int | None = None
        for i, (_, ln) in enumerate(lines):
            if ln.startswith("Description") and "Incoming" in ln and "Outgoing" in ln:
                start = i + 1
                break
        if start is None:
            raise AdapterParseError(
                self.id,
                "did not find 'Description Incoming Outgoing Amount' header",
                page=1,
            )

        results: list[ParsedTransaction] = []
        block: list[tuple[int, str]] = []
        for pno, ln in lines[start:]:
            if any(ln.startswith(p) for p in _TRAILER_PREFIXES):
                break
            block.append((pno, ln))
            if _DATE_LINE_RE.match(ln) and len(block) >= 2:
                results.append(self._make_tx(block, currency))
                block = []
        return results

    def _make_tx(
        self, block: list[tuple[int, str]], currency: str
    ) -> ParsedTransaction:
        first_pno, first = block[0]
        m_amt = _AMOUNT_BALANCE_RE.search(first)
        if m_amt is None:
            raise AdapterParseError(
                self.id,
                f"missing amount/balance trailer on first line: {first!r}",
                page=first_pno,
            )
        desc_head = first[: m_amt.start()].strip()
        amount_minor = _parse_minor(m_amt.group("amount"))

        last_pno, last = block[-1]
        d = _DATE_LINE_RE.match(last)
        if d is None:
            raise AdapterParseError(
                self.id,
                f"transaction block does not end in a date line: {last!r}",
                page=last_pno,
            )
        posted = date(
            year=int(d.group("year")),
            month=_MONTHS[d.group("month")],
            day=int(d.group("day")),
        )

        continuations = [ln for _, ln in block[1:-1]]
        payee = desc_head
        if continuations:
            payee = (desc_head + " " + " ".join(continuations)).strip()

        memo_text = last[d.end() :].strip()
        memo = memo_text or None

        return ParsedTransaction(
            posted_date=posted,
            amount_minor=amount_minor,
            currency=currency,
            payee=payee,
            memo=memo,
        )
