"""Wire each service as a registered `Operation`."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from finance.core.operations.models import (
    AccountBalanceIn,
    AccountBalanceOut,
    AccountBalanceRow,
    AccountBalanceSnapshotIn,
    AccountBalanceSnapshotOut,
    AccountOut,
    AdapterOut,
    ArchiveAccountIn,
    ArchiveAccountOut,
    ConfirmDraftIn,
    ConfirmDraftOut,
    CreateAccountIn,
    CreateAccountOut,
    DeleteTransactionIn,
    DeleteTransactionOut,
    DraftOut,
    ImportArtifactIn,
    ImportArtifactOut,
    IncomeExpenseBlockOut,
    IncomeExpenseForMonthIn,
    IncomeExpenseForMonthOut,
    ListAccountsIn,
    ListAccountsOut,
    ListAdaptersIn,
    ListAdaptersOut,
    ListDraftsIn,
    ListDraftsOut,
    ListTransactionsIn,
    ListTransactionsOut,
    MonthlySummaryIn,
    MonthlySummaryOut,
    RecordTransactionIn,
    RecordTransactionOut,
    RejectDraftIn,
    RejectDraftOut,
    TransactionOut,
    UpdateTransactionIn,
    UpdateTransactionOut,
)
from finance.core.operations.operation import Operation
from finance.core.operations.registry import OperationRegistry
from finance.core.services import (
    account_balance,
    archive_account,
    create_account,
    delete_transaction,
    list_accounts,
    list_transactions,
    record_transaction,
    update_transaction,
)


def _create_account(session: Session, payload: CreateAccountIn) -> CreateAccountOut:
    account = create_account(
        session,
        name=payload.name,
        currency=payload.currency,
        opening_balance_minor=payload.opening_balance_minor,
    )
    return CreateAccountOut(account=AccountOut.model_validate(account))


def _archive_account(session: Session, payload: ArchiveAccountIn) -> ArchiveAccountOut:
    account = archive_account(session, account_id=payload.account_id)
    return ArchiveAccountOut(account=AccountOut.model_validate(account))


def _list_accounts(session: Session, payload: ListAccountsIn) -> ListAccountsOut:
    accounts = list_accounts(session, include_archived=payload.include_archived)
    return ListAccountsOut(accounts=[AccountOut.model_validate(a) for a in accounts])


def _record_transaction(session: Session, payload: RecordTransactionIn) -> RecordTransactionOut:
    tx = record_transaction(
        session,
        account_id=payload.account_id,
        posted_date=payload.posted_date,
        amount_minor=payload.amount_minor,
        currency=payload.currency,
        payee=payload.payee,
        memo=payload.memo,
        entered_by=payload.entered_by,
    )
    return RecordTransactionOut(transaction=TransactionOut.model_validate(tx))


def _update_transaction(session: Session, payload: UpdateTransactionIn) -> UpdateTransactionOut:
    tx = update_transaction(
        session,
        transaction_id=payload.transaction_id,
        posted_date=payload.posted_date,
        amount_minor=payload.amount_minor,
        payee=payload.payee,
        memo=payload.memo,
    )
    return UpdateTransactionOut(transaction=TransactionOut.model_validate(tx))


def _delete_transaction(session: Session, payload: DeleteTransactionIn) -> DeleteTransactionOut:
    delete_transaction(session, transaction_id=payload.transaction_id)
    return DeleteTransactionOut()


def _list_transactions(session: Session, payload: ListTransactionsIn) -> ListTransactionsOut:
    rows = list_transactions(
        session,
        account_id=payload.account_id,
        start=payload.start,
        end=payload.end,
    )
    return ListTransactionsOut(transactions=[TransactionOut.model_validate(t) for t in rows])


def _account_balance(session: Session, payload: AccountBalanceIn) -> AccountBalanceOut:
    money = account_balance(session, account_id=payload.account_id)
    return AccountBalanceOut(
        account_id=payload.account_id,
        currency=money.currency,
        balance_minor=money.minor,
    )


# --- Ingestion ---------------------------------------------------------------
# Imported lazily to avoid circular imports at module load time: ingestion
# imports core but core does not import ingestion at top level.
def _list_adapters(session: Session, payload: ListAdaptersIn) -> ListAdaptersOut:
    del session, payload
    from finance.ingestion import build_default_adapter_registry

    registry = build_default_adapter_registry()
    adapters = [
        AdapterOut(
            id=a.id,
            display_name=a.display_name,
            source_artifact_type=a.source_artifact_type,
        )
        for a in registry.list_adapters()
    ]
    return ListAdaptersOut(adapters=adapters)


def _import_artifact(session: Session, payload: ImportArtifactIn) -> ImportArtifactOut:
    from finance.ingestion import build_default_adapter_registry
    from finance.ingestion.pipeline import import_artifact

    result = import_artifact(
        session,
        adapter_id=payload.adapter_id,
        path=Path(payload.path),
        account_id=payload.account_id,
        registry=build_default_adapter_registry(),
        force=payload.force,
    )
    return ImportArtifactOut(
        batch_id=result.batch_id,
        adapter_id=result.adapter_id,
        account_id=result.account_id,
        draft_count=result.draft_count,
        duplicates_skipped=result.duplicates_skipped,
        source_sha256=result.source_sha256,
        source_filename=result.source_filename,
        source_size_bytes=result.source_size_bytes,
    )


def _list_drafts(session: Session, payload: ListDraftsIn) -> ListDraftsOut:
    from finance.core.models import DraftStatus
    from finance.ingestion.pipeline import list_drafts

    status = DraftStatus(payload.status) if payload.status is not None else None
    rows = list_drafts(
        session,
        account_id=payload.account_id,
        batch_id=payload.batch_id,
        status=status,
        limit=payload.limit,
    )
    return ListDraftsOut(drafts=[DraftOut.model_validate(r) for r in rows])


def _confirm_draft(session: Session, payload: ConfirmDraftIn) -> ConfirmDraftOut:
    from finance.ingestion.review import confirm_draft

    tx = confirm_draft(session, draft_id=payload.draft_id)
    return ConfirmDraftOut(
        transaction=TransactionOut.model_validate(tx),
        draft_id=payload.draft_id,
    )


def _reject_draft(session: Session, payload: RejectDraftIn) -> RejectDraftOut:
    from finance.ingestion.review import reject_draft

    draft = reject_draft(session, draft_id=payload.draft_id)
    return RejectDraftOut(draft=DraftOut.model_validate(draft))


# --- Reporting --------------------------------------------------------------


def _block_to_out(block: object) -> IncomeExpenseBlockOut:
    # Avoid importing the dataclass at module top level just to write a tiny
    # adapter function. The dataclass attributes match the model fields 1:1.
    return IncomeExpenseBlockOut(
        currency=block.currency,  # type: ignore[attr-defined]
        income_minor=block.income_minor,  # type: ignore[attr-defined]
        expense_minor=block.expense_minor,  # type: ignore[attr-defined]
        net_savings_minor=block.net_savings_minor,  # type: ignore[attr-defined]
        savings_rate=block.savings_rate,  # type: ignore[attr-defined]
        transaction_count=block.transaction_count,  # type: ignore[attr-defined]
    )


def _monthly_summary(session: Session, payload: MonthlySummaryIn) -> MonthlySummaryOut:
    from finance.reporting.queries import monthly_summary

    summary = monthly_summary(session, year=payload.year, month=payload.month)
    return MonthlySummaryOut(
        year=summary.year,
        month=summary.month,
        start=summary.start,
        end=summary.end,
        blocks=[_block_to_out(b) for b in summary.blocks],
    )


def _income_expense_for_month(
    session: Session, payload: IncomeExpenseForMonthIn
) -> IncomeExpenseForMonthOut:
    from finance.reporting.queries import income_expense_for_month

    block = income_expense_for_month(
        session, year=payload.year, month=payload.month, currency=payload.currency
    )
    return IncomeExpenseForMonthOut(
        year=payload.year,
        month=payload.month,
        block=_block_to_out(block),
    )


def _account_balance_snapshot(
    session: Session, payload: AccountBalanceSnapshotIn
) -> AccountBalanceSnapshotOut:
    del payload
    from finance.reporting.queries import account_balance_snapshot

    rows = account_balance_snapshot(session)
    return AccountBalanceSnapshotOut(
        accounts=[
            AccountBalanceRow(
                account_id=r.account_id,
                name=r.name,
                currency=r.currency,
                balance_minor=r.balance_minor,
            )
            for r in rows
        ]
    )


_OPERATIONS: tuple[Operation, ...] = (
    Operation(
        name="create_account",
        input_model=CreateAccountIn,
        output_model=CreateAccountOut,
        callable=_create_account,
        description="Create a new active account.",
        tags=("ledger", "accounts"),
    ),
    Operation(
        name="archive_account",
        input_model=ArchiveAccountIn,
        output_model=ArchiveAccountOut,
        callable=_archive_account,
        description="Soft-delete an account that has no transactions.",
        tags=("ledger", "accounts"),
    ),
    Operation(
        name="list_accounts",
        input_model=ListAccountsIn,
        output_model=ListAccountsOut,
        callable=_list_accounts,
        description="List accounts; archived ones are excluded by default.",
        tags=("ledger", "accounts"),
    ),
    Operation(
        name="record_transaction",
        input_model=RecordTransactionIn,
        output_model=RecordTransactionOut,
        callable=_record_transaction,
        description="Record a transaction against an account.",
        tags=("ledger", "transactions"),
    ),
    Operation(
        name="update_transaction",
        input_model=UpdateTransactionIn,
        output_model=UpdateTransactionOut,
        callable=_update_transaction,
        description="Update editable fields on an existing transaction.",
        tags=("ledger", "transactions"),
    ),
    Operation(
        name="delete_transaction",
        input_model=DeleteTransactionIn,
        output_model=DeleteTransactionOut,
        callable=_delete_transaction,
        description="Delete a transaction by id.",
        tags=("ledger", "transactions"),
    ),
    Operation(
        name="list_transactions",
        input_model=ListTransactionsIn,
        output_model=ListTransactionsOut,
        callable=_list_transactions,
        description="List transactions for an account, optionally filtered by date.",
        tags=("ledger", "transactions"),
    ),
    Operation(
        name="account_balance",
        input_model=AccountBalanceIn,
        output_model=AccountBalanceOut,
        callable=_account_balance,
        description="Compute current balance for an account.",
        tags=("ledger", "balances"),
    ),
    Operation(
        name="list_adapters",
        input_model=ListAdaptersIn,
        output_model=ListAdaptersOut,
        callable=_list_adapters,
        description="List installed institution adapters.",
        tags=("ingestion", "adapters"),
    ),
    Operation(
        name="import_artifact",
        input_model=ImportArtifactIn,
        output_model=ImportArtifactOut,
        callable=_import_artifact,
        description="Run an institution adapter against a file and persist drafts.",
        tags=("ingestion",),
    ),
    Operation(
        name="list_drafts",
        input_model=ListDraftsIn,
        output_model=ListDraftsOut,
        callable=_list_drafts,
        description="List draft transactions, filterable by account/batch/status.",
        tags=("ingestion", "drafts"),
    ),
    Operation(
        name="confirm_draft",
        input_model=ConfirmDraftIn,
        output_model=ConfirmDraftOut,
        callable=_confirm_draft,
        description="Promote a pending draft to a canonical transaction.",
        tags=("ingestion", "drafts"),
    ),
    Operation(
        name="reject_draft",
        input_model=RejectDraftIn,
        output_model=RejectDraftOut,
        callable=_reject_draft,
        description="Mark a pending draft as rejected.",
        tags=("ingestion", "drafts"),
    ),
    Operation(
        name="monthly_summary",
        input_model=MonthlySummaryIn,
        output_model=MonthlySummaryOut,
        callable=_monthly_summary,
        description="Calendar-month summary; one block per currency present.",
        tags=("reporting",),
    ),
    Operation(
        name="income_expense_for_month",
        input_model=IncomeExpenseForMonthIn,
        output_model=IncomeExpenseForMonthOut,
        callable=_income_expense_for_month,
        description="Income/expense/net/savings-rate for one (year, month, currency).",
        tags=("reporting",),
    ),
    Operation(
        name="account_balance_snapshot",
        input_model=AccountBalanceSnapshotIn,
        output_model=AccountBalanceSnapshotOut,
        callable=_account_balance_snapshot,
        description="Per-account balance snapshot for non-archived accounts.",
        tags=("reporting", "balances"),
    ),
)


def register_all(registry: OperationRegistry) -> None:
    """Register every built-in operation on the given registry."""
    for op in _OPERATIONS:
        registry.register(op)


def build_default_registry() -> OperationRegistry:
    """Return a fresh registry with all built-in operations registered."""
    registry = OperationRegistry()
    register_all(registry)
    return registry
