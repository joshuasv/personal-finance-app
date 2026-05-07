"""Ingestion pipeline: artifact in, drafts out.

Runs an `InstitutionAdapter` against a source file, persists the parsed lines
as `DraftTransaction` rows, and groups them into an `IngestionBatch`. The
canonical ledger is untouched until a user confirms a draft (see `review`).
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from finance.core.models import DraftStatus, DraftTransaction, IngestionBatch
from finance.core.repositories.accounts import AccountRepository
from finance.core.services.accounts import AccountNotFoundError
from finance.core.services.errors import (
    AccountArchivedError,
    CurrencyMismatchError,
    ValidationError,
)
from finance.core.services.transactions import compute_content_hash
from finance.ingestion.registry import AdapterRegistry


class AdapterNotFoundError(ValidationError):
    """The caller asked for an adapter that is not registered."""


class DuplicateBatchError(ValidationError):
    """The same source artifact has already been ingested.

    Carries the existing batch so callers can show context. Raise this only
    when the caller did not pass `force=True`.
    """

    def __init__(self, batch: IngestionBatch):
        self.batch = batch
        super().__init__(
            f"this PDF has already been ingested as batch {batch.id} "
            f"(adapter {batch.adapter_id}, account {batch.account_id}); "
            "pass force=True to import it again"
        )


@dataclass(frozen=True, slots=True)
class ImportResult:
    """Summary of one `import_artifact` run."""

    batch_id: int
    adapter_id: str
    account_id: int
    draft_count: int
    duplicates_skipped: int
    source_sha256: str
    source_filename: str
    source_size_bytes: int


def _hash_file(path: Path) -> tuple[str, int]:
    h = hashlib.sha256()
    size = 0
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(64 * 1024), b""):
            h.update(chunk)
            size += len(chunk)
    return h.hexdigest(), size


def import_artifact(
    session: Session,
    *,
    adapter_id: str,
    path: Path | str,
    account_id: int,
    registry: AdapterRegistry,
    force: bool = False,
) -> ImportResult:
    """Parse an artifact and persist its lines as drafts under a new batch.

    Refuses to run if the source's sha256 already matches a prior batch unless
    `force=True`. Currency-mismatch and parser failures abort cleanly without
    writing any draft rows.
    """
    if not registry.has(adapter_id):
        known = ", ".join(a.id for a in registry.list_adapters()) or "(none)"
        raise AdapterNotFoundError(f"unknown adapter {adapter_id!r}; known adapters: {known}")
    adapter = registry.get_adapter(adapter_id)

    account = AccountRepository(session).get(account_id)
    if account is None:
        raise AccountNotFoundError(f"no account with id {account_id}")
    if account.archived:
        raise AccountArchivedError(
            f"account {account.name!r} is archived and cannot ingest statements"
        )

    artifact_path = Path(path).expanduser()
    if not artifact_path.is_file():
        raise ValidationError(f"artifact path does not exist: {artifact_path}")

    sha256, size_bytes = _hash_file(artifact_path)

    if not force:
        prior = session.query(IngestionBatch).filter(IngestionBatch.source_sha256 == sha256).first()
        if prior is not None:
            raise DuplicateBatchError(prior)

    parsed = list(adapter.parse(artifact_path))

    # Currency validation: every parsed line must match the account's currency.
    for line in parsed:
        if line.currency.upper() != account.currency:
            raise CurrencyMismatchError(
                f"adapter {adapter_id!r} produced a {line.currency!r} line for "
                f"account {account.name!r} ({account.currency}); refusing to import"
            )

    batch = IngestionBatch(
        adapter_id=adapter_id,
        source_filename=artifact_path.name,
        source_size_bytes=size_bytes,
        source_sha256=sha256,
        account_id=account_id,
        draft_count=0,
    )
    session.add(batch)
    session.flush()

    seen_hashes: set[str] = set()
    drafts_written = 0
    duplicates_skipped = 0
    for line in parsed:
        content_hash = compute_content_hash(
            account_id=account_id,
            posted_date=line.posted_date,
            amount_minor=line.amount_minor,
            currency=account.currency,
            payee=line.payee,
            memo=line.memo,
        )
        if content_hash in seen_hashes:
            duplicates_skipped += 1
            continue
        seen_hashes.add(content_hash)

        draft = DraftTransaction(
            batch_id=batch.id,
            account_id=account_id,
            posted_date=line.posted_date,
            amount_minor=line.amount_minor,
            currency=account.currency,
            payee=line.payee,
            memo=line.memo,
            status=DraftStatus.pending,
            content_hash=content_hash,
        )
        session.add(draft)
        drafts_written += 1

    batch.draft_count = drafts_written
    session.flush()

    return ImportResult(
        batch_id=batch.id,
        adapter_id=adapter_id,
        account_id=account_id,
        draft_count=drafts_written,
        duplicates_skipped=duplicates_skipped,
        source_sha256=sha256,
        source_filename=artifact_path.name,
        source_size_bytes=size_bytes,
    )


def list_drafts(
    session: Session,
    *,
    account_id: int | None = None,
    batch_id: int | None = None,
    status: DraftStatus | None = DraftStatus.pending,
    limit: int | None = None,
) -> Sequence[DraftTransaction]:
    """List drafts with optional filters; defaults to pending across all accounts."""
    q = session.query(DraftTransaction)
    if account_id is not None:
        q = q.filter(DraftTransaction.account_id == account_id)
    if batch_id is not None:
        q = q.filter(DraftTransaction.batch_id == batch_id)
    if status is not None:
        q = q.filter(DraftTransaction.status == status)
    q = q.order_by(DraftTransaction.posted_date, DraftTransaction.id)
    if limit is not None:
        q = q.limit(limit)
    return q.all()


# Re-export for callers that prefer one import.
__all__ = [
    "AdapterNotFoundError",
    "DuplicateBatchError",
    "ImportResult",
    "import_artifact",
    "list_drafts",
]
