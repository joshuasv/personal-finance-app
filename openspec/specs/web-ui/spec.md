# web-ui

## Purpose

Browser UI (React + Vite) for visual review of transactions, the draft review queue, and the monthly summary.

## Requirements

### Requirement: React + Vite web app
The system SHALL ship a React + TypeScript single-page application built with Vite, located at `src/finance/web/`. In development the app SHALL run on `:5173` and proxy `/api/*` to the FastAPI process. In production the built `dist/` SHALL be servable as static assets by `finance serve --with-ui`.

#### Scenario: Dev server proxies API requests
- **GIVEN** `finance serve` running on `:8000` and `npm run dev` running on `:5173`
- **WHEN** the SPA fetches `/api/transactions`
- **THEN** Vite's dev proxy forwards the request to `http://127.0.0.1:8000/api/transactions` and returns the response

#### Scenario: Bundled mode serves the SPA
- **WHEN** the user runs `finance serve --with-ui`
- **THEN** `GET /` returns the SPA's `index.html` and SPA routes fall back to `index.html` (single-page-app routing)

### Requirement: Authentication via API key
The web UI SHALL prompt the user for the API key on first load, store it in browser local storage, and send it as `Authorization: Bearer <key>` on every API request. A "log out" action SHALL clear the stored key.

#### Scenario: First-load prompt
- **GIVEN** a fresh browser with no stored key
- **WHEN** the user opens the web UI
- **THEN** a key-entry form is shown and no API requests are made until the user submits a key

#### Scenario: 401 forces re-prompt
- **WHEN** any API request returns `401`
- **THEN** the stored key is cleared and the key-entry form is shown again

### Requirement: Transactions view
The web UI SHALL provide a Transactions view that lists confirmed transactions with columns for date, account, payee, and amount (sign-correct, currency-formatted). The view SHALL support filtering by account and month.

#### Scenario: Filter by account
- **WHEN** the user selects account "Wise GBP" in the Transactions view filter
- **THEN** the table shows only transactions on the "Wise GBP" account

#### Scenario: Empty state
- **WHEN** no transactions match the active filters
- **THEN** the view shows an empty-state message with a hint to clear filters or import a statement

### Requirement: Drafts review view
The web UI SHALL provide a Drafts view listing pending drafts grouped by ingestion batch. Each draft row SHALL show date, payee, amount, and Confirm / Reject buttons. The view SHALL support a "Confirm all in this batch" bulk action.

#### Scenario: Confirm a draft
- **WHEN** the user clicks Confirm on a draft row
- **THEN** the corresponding API confirm call is made and the row disappears from the pending list

#### Scenario: Reject a draft
- **WHEN** the user clicks Reject on a draft row
- **THEN** the corresponding API reject call is made and the row disappears from the pending list

#### Scenario: Bulk confirm
- **WHEN** the user clicks "Confirm all in this batch" on a batch with K pending drafts
- **THEN** K confirm calls are issued (or one bulk call if the API supports it) and all rows disappear from the pending list as each succeeds

### Requirement: Monthly summary view
The web UI SHALL provide a Summary view showing the monthly summary for a chosen month (default: current month). The view SHALL render income, expense, net savings, and savings rate.

#### Scenario: Switch month
- **WHEN** the user selects a different month in the Summary view
- **THEN** the view fetches and renders the summary for that month

#### Scenario: Multi-currency month
- **GIVEN** the chosen month contains transactions in two currencies
- **WHEN** the user opens the Summary view for that month
- **THEN** each currency is rendered as its own summary block; no values are converted

### Requirement: Accounts view
The web UI SHALL provide an Accounts view listing each non-archived account with its name, type, currency, and current balance, and offer a "New account" form. Submitting the form SHALL call the corresponding API operation.

#### Scenario: Create account from the UI
- **WHEN** the user submits the New Account form with valid fields
- **THEN** the corresponding API operation is called and on success the new account appears in the list

### Requirement: Mobile-responsive layout
The web UI SHALL be usable on a mobile-sized viewport (≤ 480px wide): primary navigation collapses, tables become vertically stacked card lists, and tap targets are at least 44px on a side.

#### Scenario: Mobile viewport renders the Transactions list as cards
- **WHEN** the viewport is 375px wide
- **THEN** the Transactions view renders one card per transaction (date, payee, amount) instead of a table

### Requirement: No business logic in the UI
The web UI MUST NOT compute balances or summaries client-side; all such values SHALL come from API responses. Client logic is restricted to display formatting (currency, date), filter state, and form validation that mirrors API constraints.

#### Scenario: Summary numbers come from the API
- **WHEN** the Summary view renders income, expense, net savings, savings rate
- **THEN** these values come directly from the monthly-summary API response and are not recomputed in the browser
