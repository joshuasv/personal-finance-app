"""Generate synthetic Wise statement PDF fixtures.

Run once (or when fixture content changes):
    python tests/fixtures/wise/_generate.py

The generated PDFs contain entirely fictitious data — fake name, fake IBAN,
fake transactions. No real personal or financial data is used.
"""

from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# Synthetic statement text — US ordering ("Month Day, Year")
# ---------------------------------------------------------------------------
# Designed so the unit tests can assert:
#   - len(parsed) > 20
#   - EUR currency, non-zero amounts, non-empty payees, year=2026, month=4
#   - Netto -6.55 EUR (amount_minor=-655) on April 30
#   - SKD SE salary 3971.93 EUR (amount_minor=397193) with "LOHN" in payee
#   - at least one inflow and one outflow
_US_LINES = """\
Wise Europe SA
Rue du Trone 100, 3rd floor
Brussels 1050 Belgium
EUR statement
April 1, 2026 [GMT+02:00] - April 30, 2026 [GMT+02:00]
Generated on: May 1, 2026
Account Holder IBAN Swift/BIC
Test User XX00 0000 0000 0000 TRWIBEB1XXX
Test Address, Test City 00000 Test Country
EUR on April 30, 2026 [GMT+02:00] 5,000.00 EUR
Description Incoming Outgoing Amount
Card transaction of 6.55 EUR issued by Netto Marken-Discount Berlin -6.55 5,000.00
April 30, 2026 Card ending in 0000 Test User Transaction: CARD-0000000001
Card transaction of 21.42 EUR issued by Test Service Online -21.42 5,006.55
April 29, 2026 Card ending in 0000 Test User Transaction: CARD-0000000002
Card transaction of 15.00 EUR issued by Test Supermarket Berlin -15.00 5,027.97
April 28, 2026 Card ending in 0000 Test User Transaction: CARD-0000000003
Received money from SKD SE with reference LOHN / GEHALT 04/26 3,971.93 5,042.97
/0000000000-0000000000
April 28, 2026 Transaction: TRANSFER-0000000001 Reference: LOHN / GEHALT 04/26
Card transaction of 25.00 EUR issued by Test Bakery Berlin -25.00 1,071.04
April 27, 2026 Card ending in 0000 Test User Transaction: CARD-0000000004
Paid to Test Company GmbH -100.00 1,096.04
April 26, 2026 Transaction: DIRECT_DEBIT-0000000001 Reference: TEST-REF-001
Card transaction of 8.50 EUR issued by Test Cafe Berlin -8.50 1,196.04
April 25, 2026 Card ending in 0000 Test User Transaction: CARD-0000000005
Card transaction of 12.00 EUR issued by Test Restaurant Berlin -12.00 1,204.54
April 24, 2026 Card ending in 0000 Test User Transaction: CARD-0000000006
Card transaction of 5.99 EUR issued by Test Market Berlin -5.99 1,216.54
April 23, 2026 Card ending in 0000 Test User Transaction: CARD-0000000007
Received money from Test Person with reference gift 50.00 1,222.53
April 22, 2026 Transaction: TRANSFER-0000000002 Reference: gift
Card transaction of 18.00 EUR issued by Test Gym Berlin -18.00 1,172.53
April 21, 2026 Card ending in 0000 Test User Transaction: CARD-0000000008
Card transaction of 30.00 EUR issued by Test Store Berlin -30.00 1,190.53
April 20, 2026 Card ending in 0000 Test User Transaction: CARD-0000000009
Card transaction of 7.50 EUR issued by Test Kiosk Berlin -7.50 1,220.53
April 19, 2026 Card ending in 0000 Test User Transaction: CARD-0000000010
Paid to Test Utility AG -45.00 1,228.03
April 18, 2026 Transaction: DIRECT_DEBIT-0000000002 Reference: TEST-REF-002
Card transaction of 22.00 EUR issued by Test Shop Online -22.00 1,273.03
April 17, 2026 Card ending in 0000 Test User Transaction: CARD-0000000011
Card transaction of 9.00 EUR issued by Test Pharmacy Berlin -9.00 1,295.03
April 16, 2026 Card ending in 0000 Test User Transaction: CARD-0000000012
Card transaction of 14.00 EUR issued by Test Clothing Berlin -14.00 1,304.03
April 15, 2026 Card ending in 0000 Test User Transaction: CARD-0000000013
Card transaction of 3.50 EUR issued by Test Drink Berlin -3.50 1,318.03
April 14, 2026 Card ending in 0000 Test User Transaction: CARD-0000000014
Received money from Test Company 2 with reference salary bonus 200.00 1,321.53
April 13, 2026 Transaction: TRANSFER-0000000003 Reference: salary bonus
Card transaction of 11.00 EUR issued by Test Electronics Berlin -11.00 1,121.53
April 12, 2026 Card ending in 0000 Test User Transaction: CARD-0000000015
Card transaction of 6.00 EUR issued by Test Bakery Berlin -6.00 1,132.53
April 11, 2026 Card ending in 0000 Test User Transaction: CARD-0000000016
Card transaction of 4.00 EUR issued by Test Kiosk 2 Berlin -4.00 1,138.53
April 10, 2026 Card ending in 0000 Test User Transaction: CARD-0000000017
Sent money to Test Recipient -50.00 1,142.53
April 9, 2026 Transaction: TRANSFER-0000000004 Reference: TEST-REF-004
Wise is the trading name of TransferWise Ltd
Need help? Visit wise.com/help\
""".splitlines()

# ---------------------------------------------------------------------------
# Synthetic statement text — EU ordering ("Day Month Year")
# ---------------------------------------------------------------------------
# Designed so the unit tests can assert:
#   - len(parsed) > 20
#   - EUR currency, non-zero amounts, non-empty payees, year=2026, month=5
#   - Claude.ai -21.42 EUR (amount_minor=-2142) on May 31
#   - single-digit days: 1-9 May present
#   - at least one inflow and one outflow
_EU_LINES = """\
Wise Europe SA
Rue du Trone 100, 3rd floor
Brussels 1050 Belgium
EUR statement
1 May 2026 [GMT+02:00] - 31 May 2026 [GMT+02:00]
Generated on: 1 June 2026
Account Holder IBAN Swift/BIC
Test User XX00 0000 0000 0000 TRWIBEB1XXX
Test Address, Test City 00000 Test Country
EUR on 31 May 2026 [GMT+02:00] 5,000.00 EUR
Description Incoming Outgoing Amount
Card transaction of 21.42 EUR issued by Claude.ai Subscription ANTHROPIC. -21.42 5,000.00
COM
31 May 2026 Card ending in 0000 Test User Transaction: CARD-0000000001
Card transaction of 10.00 EUR issued by Test Shop Berlin -10.00 5,021.42
30 May 2026 Card ending in 0000 Test User Transaction: CARD-0000000002
Card transaction of 15.00 EUR issued by Test Supermarket Berlin -15.00 5,031.42
29 May 2026 Card ending in 0000 Test User Transaction: CARD-0000000003
Received money from SKD SE with reference LOHN / GEHALT 05/26 3,552.43 5,046.42
/0000000000-0000000000
27 May 2026 Transaction: TRANSFER-0000000001 Reference: LOHN / GEHALT 05/26
Card transaction of 8.00 EUR issued by Test Cafe Berlin -8.00 1,494.00
25 May 2026 Card ending in 0000 Test User Transaction: CARD-0000000004
Card transaction of 12.00 EUR issued by Test Restaurant Berlin -12.00 1,502.00
24 May 2026 Card ending in 0000 Test User Transaction: CARD-0000000005
Card transaction of 5.99 EUR issued by Test Market Berlin -5.99 1,514.00
23 May 2026 Card ending in 0000 Test User Transaction: CARD-0000000006
Card transaction of 18.00 EUR issued by Test Gym Berlin -18.00 1,519.99
21 May 2026 Card ending in 0000 Test User Transaction: CARD-0000000007
Card transaction of 30.00 EUR issued by Test Store Berlin -30.00 1,537.99
20 May 2026 Card ending in 0000 Test User Transaction: CARD-0000000008
Card transaction of 7.50 EUR issued by Test Kiosk Berlin -7.50 1,567.99
19 May 2026 Card ending in 0000 Test User Transaction: CARD-0000000009
Card transaction of 45.00 EUR issued by Test Service Berlin -45.00 1,575.49
18 May 2026 Card ending in 0000 Test User Transaction: CARD-0000000010
Card transaction of 22.00 EUR issued by Test Shop Online -22.00 1,620.49
17 May 2026 Card ending in 0000 Test User Transaction: CARD-0000000011
Card transaction of 9.00 EUR issued by Test Pharmacy Berlin -9.00 1,642.49
15 May 2026 Card ending in 0000 Test User Transaction: CARD-0000000012
Card transaction of 14.00 EUR issued by Test Clothing Berlin -14.00 1,651.49
14 May 2026 Card ending in 0000 Test User Transaction: CARD-0000000013
Card transaction of 3.50 EUR issued by Test Drink Berlin -3.50 1,665.49
13 May 2026 Card ending in 0000 Test User Transaction: CARD-0000000014
Received money from Test Person 2 with reference refund 25.00 1,668.99
12 May 2026 Transaction: TRANSFER-0000000002 Reference: refund
Card transaction of 11.00 EUR issued by Test Electronics Berlin -11.00 1,643.99
9 May 2026 Card ending in 0000 Test User Transaction: CARD-0000000015
Card transaction of 6.00 EUR issued by Test Bakery Berlin -6.00 1,654.99
8 May 2026 Card ending in 0000 Test User Transaction: CARD-0000000016
Card transaction of 4.00 EUR issued by Test Drink 2 Berlin -4.00 1,660.99
7 May 2026 Card ending in 0000 Test User Transaction: CARD-0000000017
Card transaction of 3.00 EUR issued by Test Snack Berlin -3.00 1,664.99
6 May 2026 Card ending in 0000 Test User Transaction: CARD-0000000018
Card transaction of 20.00 EUR issued by Test Cinema Berlin -20.00 1,667.99
5 May 2026 Card ending in 0000 Test User Transaction: CARD-0000000019
Card transaction of 16.00 EUR issued by Test Books Berlin -16.00 1,687.99
4 May 2026 Card ending in 0000 Test User Transaction: CARD-0000000020
Card transaction of 8.00 EUR issued by Test Stationery Berlin -8.00 1,703.99
3 May 2026 Card ending in 0000 Test User Transaction: CARD-0000000021
Card transaction of 12.00 EUR issued by Test Electronics 2 Berlin -12.00 1,711.99
2 May 2026 Card ending in 0000 Test User Transaction: CARD-0000000022
Sent money to Test Transfer -100.00 1,723.99
1 May 2026 Transaction: TRANSFER-0000000003 Reference: TEST-REF-003
Wise is the trading name of TransferWise Ltd
Need help? Visit wise.com/help\
""".splitlines()


def build_text_pdf(lines: list[str]) -> bytes:
    """Create a minimal single-page PDF readable by pdfplumber from text lines."""
    content_parts = [b"BT\n/F1 9 Tf\n40 2950 Td\n"]
    for line in lines:
        escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        content_parts.append(f"({escaped}) Tj\n0 -11 Td\n".encode())
    content_parts.append(b"ET\n")
    content = b"".join(content_parts)

    pdf = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []

    def add_obj(n: int, data: bytes) -> None:
        offsets.append(len(pdf))
        pdf.extend(f"{n} 0 obj\n".encode() + data + b"\nendobj\n")

    add_obj(1, b"<</Type /Catalog /Pages 2 0 R>>")
    add_obj(2, b"<</Type /Pages /Kids [3 0 R] /Count 1>>")
    add_obj(
        3,
        b"<</Type /Page /Parent 2 0 R /MediaBox [0 0 612 3000]"
        b" /Contents 4 0 R /Resources <</Font <</F1 5 0 R>>>>>>",
    )
    add_obj(
        4,
        f"<</Length {len(content)}>>".encode() + b"\nstream\n" + content + b"endstream",
    )
    add_obj(5, b"<</Type /Font /Subtype /Type1 /BaseFont /Courier>>")

    startxref = len(pdf)
    pdf.extend(b"xref\n0 6\n0000000000 65535 f \n")
    for off in offsets:
        pdf.extend(f"{off:010d} 00000 n \n".encode())
    pdf.extend(
        b"trailer\n<</Size 6 /Root 1 0 R>>\nstartxref\n" + f"{startxref}\n".encode() + b"%%EOF\n"
    )
    return bytes(pdf)


def main() -> None:
    here = Path(__file__).parent
    us_pdf = here / "april_2026.pdf"
    eu_pdf = here / "may_2026.pdf"
    us_pdf.write_bytes(build_text_pdf(_US_LINES))
    eu_pdf.write_bytes(build_text_pdf(_EU_LINES))
    print(f"written {us_pdf} ({us_pdf.stat().st_size} bytes)")
    print(f"written {eu_pdf} ({eu_pdf.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
