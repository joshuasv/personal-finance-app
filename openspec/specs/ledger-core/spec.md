# ledger-core

## Purpose

Canonical data model and operations for accounts and transactions. The single source of truth every other capability calls into.

## Requirements

### Requirement: Account model
The system SHALL represent each financial account with an id, human-readable name, 3-letter ISO 4217 currency code, opening balance in integer minor units, and a soft-deletion flag. Account names MUST be unique among non-archived accounts. The Account model SHALL NOT carry an account-type enum in v1 (no `checking | savings | credit | cash` taxonomy); future net-worth aggregation will introduce a separate `is_liability` boolean in its own change.

#### Scenario: Create a Wise GBP account
- **WHEN** the user creates an account with name "Wise GBP", currency `GBP`, opening balance `0`
- **THEN** the account exists with a generated id, the supplied fields, and `archived = false`

#### Scenario: Reject duplicate account name
- **WHEN** the user tries to create an account with a name that already exists and is not archived
- **THEN** the operation fails with a validation error and no row is created

#### Scenario: Reject non-ISO currency code
- **WHEN** the user supplies a currency string that is not a valid ISO 4217 3-letter code
- **THEN** the operation fails with a validation error

### Requirement: Transaction model
The system SHALL represent each transaction with an id, account id, posted date, amount in integer minor units (negative for outflows, positive for inflows), currency matching the account, payee text, optional memo, an `entered_by` source tag (one of: `manual`, `imported:<adapter>`), and a content hash used for de-duplication.

#### Scenario: Record a manual outflow
- **WHEN** the user records a transaction on the "Wise GBP" account for `-1250` minor units, payee "Tesco", date 2026-05-01
- **THEN** the transaction is stored with `entered_by = "manual"`, currency `GBP`, and a non-null content hash

#### Scenario: Reject currency mismatch with account
- **WHEN** the user records a transaction whose currency differs from the account's currency
- **THEN** the operation fails with a validation error

#### Scenario: Amount cannot be zero
- **WHEN** the user records a transaction with amount `0`
- **THEN** the operation fails with a validation error

### Requirement: Account balance computation
The system SHALL compute an account's current balance as the opening balance plus the sum of all transactions on that account, returned in the account's currency as integer minor units.

#### Scenario: Empty account returns opening balance
- **WHEN** an account has opening balance `10000` and no transactions
- **THEN** its current balance is `10000`

#### Scenario: Sum of inflows and outflows
- **WHEN** an account has opening balance `10000` and transactions `+5000`, `-1500`, `-200`
- **THEN** its current balance is `13300`

### Requirement: Money handled as integer minor units
All monetary values stored or transferred across operation boundaries SHALL be integers in the minor unit of the relevant currency (e.g., pence for GBP, cents for USD). The system MUST NOT use floating-point types to represent money at any persistence or API boundary.

#### Scenario: Reject float amounts at the API boundary
- **WHEN** a request supplies an amount as a JSON number with a decimal part (e.g., `12.50`)
- **THEN** the operation fails with a validation error directing the caller to use minor units

### Requirement: Schema migrations via Alembic
The system SHALL manage all schema changes through Alembic migrations. The first migration SHALL create the v1 schema. Running `finance init` on an empty database SHALL apply all migrations to head; running it on an up-to-date database SHALL be a no-op.

#### Scenario: Init on fresh database
- **WHEN** `finance init` runs against a non-existent or empty database file
- **THEN** the database file is created and contains the full v1 schema, and `alembic_version` records the head revision

#### Scenario: Init on already-migrated database
- **WHEN** `finance init` runs against a database already at head
- **THEN** the operation succeeds, the schema is unchanged, and the user receives a "no migrations to apply" message
