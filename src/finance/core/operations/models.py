"""Pydantic input/output models for every registered operation.

These doubles as FastAPI's request/response models AND the JSON Schemas the
MCP server needs. Surfaces never re-define shapes; they import from here.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from finance.core.validators import CurrencyCode, MinorUnits


class _BaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class AccountOut(_BaseModel):
    id: int
    name: str
    currency: str
    opening_balance_minor: int
    archived: bool
    created_at: datetime
    updated_at: datetime


class CreateAccountIn(_BaseModel):
    name: str = Field(min_length=1, max_length=120)
    currency: CurrencyCode
    opening_balance_minor: MinorUnits = 0


class CreateAccountOut(_BaseModel):
    account: AccountOut


class ArchiveAccountIn(_BaseModel):
    account_id: int = Field(gt=0)


class ArchiveAccountOut(_BaseModel):
    account: AccountOut


class ListAccountsIn(_BaseModel):
    include_archived: bool = False


class ListAccountsOut(_BaseModel):
    accounts: list[AccountOut]


class TransactionOut(_BaseModel):
    id: int
    account_id: int
    posted_date: date
    amount_minor: int
    currency: str
    payee: str
    memo: str | None
    entered_by: str
    content_hash: str
    created_at: datetime
    updated_at: datetime


class RecordTransactionIn(_BaseModel):
    account_id: int = Field(gt=0)
    posted_date: date
    amount_minor: MinorUnits
    currency: CurrencyCode
    payee: str = Field(min_length=1, max_length=200)
    memo: str | None = Field(default=None, max_length=2000)
    entered_by: str = Field(default="manual", min_length=1, max_length=60)


class RecordTransactionOut(_BaseModel):
    transaction: TransactionOut


class UpdateTransactionIn(_BaseModel):
    transaction_id: int = Field(gt=0)
    posted_date: date | None = None
    amount_minor: MinorUnits | None = None
    payee: str | None = Field(default=None, min_length=1, max_length=200)
    memo: str | None = Field(default=None, max_length=2000)


class UpdateTransactionOut(_BaseModel):
    transaction: TransactionOut


class DeleteTransactionIn(_BaseModel):
    transaction_id: int = Field(gt=0)


class DeleteTransactionOut(_BaseModel):
    deleted: Literal[True] = True


class ListTransactionsIn(_BaseModel):
    account_id: int = Field(gt=0)
    start: date | None = None
    end: date | None = None


class ListTransactionsOut(_BaseModel):
    transactions: list[TransactionOut]


class AccountBalanceIn(_BaseModel):
    account_id: int = Field(gt=0)


class AccountBalanceOut(_BaseModel):
    account_id: int
    currency: str
    balance_minor: int


# --- Ingestion ---------------------------------------------------------------


class AdapterOut(_BaseModel):
    id: str
    display_name: str
    source_artifact_type: str


class ListAdaptersIn(_BaseModel):
    pass


class ListAdaptersOut(_BaseModel):
    adapters: list[AdapterOut]


class ImportArtifactIn(_BaseModel):
    adapter_id: str = Field(min_length=1, max_length=60)
    path: str = Field(min_length=1)
    account_id: int = Field(gt=0)
    force: bool = False


class ImportArtifactOut(_BaseModel):
    batch_id: int
    adapter_id: str
    account_id: int
    draft_count: int
    duplicates_skipped: int
    source_sha256: str
    source_filename: str
    source_size_bytes: int


DraftStatusLiteral = Literal["pending", "confirmed", "rejected"]


class DraftOut(_BaseModel):
    id: int
    batch_id: int
    account_id: int
    posted_date: date
    amount_minor: int
    currency: str
    payee: str
    memo: str | None
    status: DraftStatusLiteral
    content_hash: str
    confirmed_transaction_id: int | None
    created_at: datetime
    updated_at: datetime


class ListDraftsIn(_BaseModel):
    account_id: int | None = Field(default=None, gt=0)
    batch_id: int | None = Field(default=None, gt=0)
    status: DraftStatusLiteral | None = "pending"
    limit: int | None = Field(default=None, gt=0, le=1000)


class ListDraftsOut(_BaseModel):
    drafts: list[DraftOut]


class ConfirmDraftIn(_BaseModel):
    draft_id: int = Field(gt=0)


class ConfirmDraftOut(_BaseModel):
    transaction: TransactionOut
    draft_id: int


class RejectDraftIn(_BaseModel):
    draft_id: int = Field(gt=0)


class RejectDraftOut(_BaseModel):
    draft: DraftOut


# --- Reporting --------------------------------------------------------------


class IncomeExpenseBlockOut(_BaseModel):
    currency: str
    income_minor: int
    expense_minor: int
    net_savings_minor: int
    savings_rate: float | None
    transaction_count: int


class MonthlySummaryIn(_BaseModel):
    year: int = Field(ge=1900, le=9999)
    month: int = Field(ge=1, le=12)


class MonthlySummaryOut(_BaseModel):
    year: int
    month: int
    start: date
    end: date
    blocks: list[IncomeExpenseBlockOut]


class IncomeExpenseForMonthIn(_BaseModel):
    year: int = Field(ge=1900, le=9999)
    month: int = Field(ge=1, le=12)
    currency: CurrencyCode


class IncomeExpenseForMonthOut(_BaseModel):
    year: int
    month: int
    block: IncomeExpenseBlockOut


class AccountBalanceRow(_BaseModel):
    account_id: int
    name: str
    currency: str
    balance_minor: int


class AccountBalanceSnapshotIn(_BaseModel):
    pass


class AccountBalanceSnapshotOut(_BaseModel):
    accounts: list[AccountBalanceRow]
