"""Draft review: confirm or reject ingested drafts.

Confirming inserts a `Transaction` row into the canonical ledger and stamps
the draft as `confirmed`. Rejecting just stamps the draft as `rejected`.
Re-actioning a non-pending draft fails with a clear error.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from finance.core.models import DraftStatus, DraftTransaction, Transaction
from finance.core.repositories.transactions import TransactionRepository
from finance.core.services.errors import NotFoundError, ValidationError
from finance.core.services.transactions import DuplicateTransactionError


class DraftNotFoundError(NotFoundError):
    pass


class DraftNotPendingError(ValidationError):
    """Caller tried to confirm or reject a draft that is no longer pending."""


def _resolve_draft(session: Session, draft_id: int) -> DraftTransaction:
    draft = session.get(DraftTransaction, draft_id)
    if draft is None:
        raise DraftNotFoundError(f"no draft with id {draft_id}")
    return draft


def confirm_draft(session: Session, *, draft_id: int) -> Transaction:
    """Promote a pending draft to a `Transaction`.

    Refuses if the draft is not pending or if the same content hash already
    exists on a transaction for the same account.
    """
    draft = _resolve_draft(session, draft_id)
    if draft.status is not DraftStatus.pending:
        raise DraftNotPendingError(f"draft {draft_id} is {draft.status.value}, not pending")

    repo = TransactionRepository(session)
    clash = repo.find_by_account_and_hash(draft.account_id, draft.content_hash)
    if clash is not None:
        raise DuplicateTransactionError(
            f"a transaction with the same date/amount/payee already exists on "
            f"account {draft.account_id} (id={clash.id}); refusing to confirm draft {draft_id}"
        )

    tx = repo.add(
        account_id=draft.account_id,
        posted_date=draft.posted_date,
        amount_minor=draft.amount_minor,
        currency=draft.currency,
        payee=draft.payee,
        entered_by=f"imported:{_adapter_id_for(draft)}",
        content_hash=draft.content_hash,
        memo=draft.memo,
    )
    draft.status = DraftStatus.confirmed
    draft.confirmed_transaction_id = tx.id
    session.flush()
    return tx


def reject_draft(session: Session, *, draft_id: int) -> DraftTransaction:
    """Mark a pending draft as rejected. No transaction is created."""
    draft = _resolve_draft(session, draft_id)
    if draft.status is not DraftStatus.pending:
        raise DraftNotPendingError(f"draft {draft_id} is {draft.status.value}, not pending")
    draft.status = DraftStatus.rejected
    session.flush()
    return draft


def _adapter_id_for(draft: DraftTransaction) -> str:
    # The batch is loaded via the relationship; if it's not yet attached,
    # SQLAlchemy will load it lazily.
    return draft.batch.adapter_id


__all__ = [
    "DraftNotFoundError",
    "DraftNotPendingError",
    "confirm_draft",
    "reject_draft",
]
