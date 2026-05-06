## ADDED Requirements

### Requirement: Monthly summary report
The system SHALL produce a monthly summary report for a given (year, month) covering all non-archived accounts. The report SHALL include: total income (sum of inflows), total expense (absolute value of sum of outflows), net savings (income minus expense), and savings rate (net savings divided by income, expressed as a percentage; null if income is zero). All money values SHALL be in integer minor units, accompanied by a currency code.

#### Scenario: Empty month returns zeros
- **WHEN** a summary is requested for a month with no transactions
- **THEN** income, expense, and net savings are `0`, and savings rate is null

#### Scenario: Mixed inflows and outflows
- **GIVEN** a month with inflows totalling `300000` GBP minor units and outflows of `-180000` GBP minor units
- **WHEN** the user requests the monthly summary
- **THEN** income is `300000`, expense is `180000`, net savings is `120000`, and savings rate is `40.0`

#### Scenario: Savings rate is null when income is zero
- **WHEN** a month has no inflows but has outflows
- **THEN** income is `0`, expense is the absolute sum of outflows, net savings is negative, and savings rate is null (not a divide-by-zero error)

#### Scenario: Drafts are excluded
- **GIVEN** a month with N pending drafts and M confirmed transactions
- **WHEN** the user requests the monthly summary
- **THEN** only the M confirmed transactions are reflected in the report

### Requirement: Per-account balance snapshot
The system SHALL produce a balance snapshot listing each non-archived account with its name, currency, and current balance (as defined by the ledger-core balance computation). Balances SHALL NOT be auto-converted across currencies; the snapshot SHALL be a list, not a single total.

#### Scenario: Multi-currency snapshot
- **GIVEN** accounts "Wise GBP" (balance `25000` GBP minor units) and "Wise EUR" (balance `40000` EUR minor units)
- **WHEN** the user requests a balance snapshot
- **THEN** the result lists both accounts with their respective balances and currency codes, and no single converted total is reported

### Requirement: Multi-currency reporting policy
When a monthly summary spans transactions in more than one currency, the report SHALL be returned per-currency (one summary block per currency present that month). The system MUST NOT convert across currencies in v1.

#### Scenario: Two currencies in one month
- **GIVEN** GBP and EUR transactions in the same month
- **WHEN** the user requests the monthly summary
- **THEN** the response contains two summary blocks, one per currency, each independently computed

### Requirement: Calendar-month boundaries
For v1, the month boundary SHALL be the calendar month in the system's local timezone. The summary's date range SHALL be `[YYYY-MM-01, YYYY-MM-(last day)]` inclusive.

#### Scenario: Boundary transaction is included
- **GIVEN** a transaction posted on 2026-05-31
- **WHEN** the user requests the May 2026 summary
- **THEN** the transaction is included in the report
