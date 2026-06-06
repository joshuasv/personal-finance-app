# statement-ingestion

## Purpose

Institution-adapter abstraction, the Wise PDF adapter, the parsing pipeline, and the draft-transaction review queue.

## Requirements

### Requirement: InstitutionAdapter protocol
The system SHALL define an `InstitutionAdapter` protocol that takes a source artifact (initially a PDF file) plus a target account id and yields zero or more `DraftTransaction` records. Each adapter SHALL declare a unique `id` (e.g., `wise-pdf`), a human-readable `display_name`, and the supported source artifact type. Adding a new institution SHALL require only a new adapter implementation registered with the adapter registry — no changes to core, API, or surface code.

#### Scenario: Adapter registry lists all built-in adapters
- **WHEN** the system starts
- **THEN** the adapter registry contains the `wise-pdf` adapter with its declared `id` and `display_name`

#### Scenario: Add a new adapter without core changes
- **GIVEN** a new `chase-pdf` adapter implementing the protocol and registered at startup
- **WHEN** the user lists available adapters via any surface
- **THEN** the new adapter appears alongside `wise-pdf` and accepts uploads

### Requirement: Wise PDF adapter
The system SHALL ship a `wise-pdf` adapter that parses Wise monthly statement PDFs and produces one `DraftTransaction` per statement line, capturing date, payee/description, amount in minor units (sign-correct), and currency.

#### Scenario: Parse a known-good Wise statement
- **GIVEN** a fixture Wise PDF with N transactions
- **WHEN** the user uploads it through the adapter targeting a Wise account
- **THEN** N draft transactions are produced with correct dates, payees, signed amounts, and currency

#### Scenario: Surface a parser failure clearly
- **WHEN** the adapter cannot parse a PDF (e.g., layout it does not recognize)
- **THEN** ingestion fails with an error message that names the adapter and the page where parsing broke, and no drafts are written

#### Scenario: Currency mismatch fails fast
- **WHEN** the user uploads a Wise statement in a currency different from the target account's currency
- **THEN** ingestion fails with a validation error and no drafts are written

### Requirement: Draft transaction model
The system SHALL store ingested-but-not-yet-confirmed transactions in a `draft_transactions` table separate from canonical `transactions`. Each draft SHALL have an id, source batch id, account id, posted date, amount in minor units, currency, payee, optional memo, status (one of `pending`, `confirmed`, `rejected`), and a content hash.

#### Scenario: Drafts do not affect balances
- **GIVEN** an account with current balance `B` and `K` pending drafts
- **WHEN** the user queries the account balance
- **THEN** the result is `B` and is independent of `K`

#### Scenario: Draft hashes deduplicate within a batch
- **WHEN** an adapter produces two draft rows with identical (account, date, amount, payee)
- **THEN** only one draft row is written and the duplicate is skipped with a logged note

### Requirement: Ingestion batch
The system SHALL group every adapter run into an `ingestion_batch` row recording the adapter id, the source artifact metadata (filename, byte size, sha256), the target account id, the count of drafts produced, and a timestamp. Drafts SHALL reference their batch.

#### Scenario: Batch records the source PDF hash
- **WHEN** the user uploads a Wise PDF through the `wise-pdf` adapter
- **THEN** an `ingestion_batch` row is created with the PDF's filename, size, and sha256

#### Scenario: Re-uploading the same PDF is detectable
- **WHEN** the user uploads a PDF whose sha256 matches a prior `ingestion_batch`
- **THEN** the system warns that the file has been ingested before and requires explicit confirmation to proceed

### Requirement: Confirm or reject drafts
The system SHALL allow the user to confirm or reject a draft. Confirming SHALL atomically insert a corresponding row into `transactions` (with `entered_by = "imported:<adapter_id>"`) and mark the draft `confirmed`. Rejecting SHALL mark the draft `rejected` and write nothing to `transactions`. Confirmed and rejected drafts SHALL NOT be re-actionable.

#### Scenario: Confirm a pending draft
- **GIVEN** a pending draft
- **WHEN** the user confirms it
- **THEN** a transaction is created on the same account with the same amount, date, payee, and memo, and the draft becomes `confirmed`

#### Scenario: Reject a draft
- **WHEN** the user rejects a pending draft
- **THEN** the draft becomes `rejected` and no transaction is created

#### Scenario: Idempotent confirmation
- **WHEN** the user confirms a draft that is already `confirmed` or `rejected`
- **THEN** the operation fails with a clear error and no new transaction is created

### Requirement: De-duplication against the canonical ledger
On confirmation, the system SHALL detect when the same content hash already exists on a `transactions` row for the same account and refuse to create a duplicate, returning a clear error that names the existing transaction.

#### Scenario: Refuse to import a transaction already present manually
- **GIVEN** a manual transaction with a given content hash on account A
- **WHEN** the user confirms a draft on account A with the same content hash
- **THEN** confirmation fails with a duplicate-detected error and the draft remains `pending`
