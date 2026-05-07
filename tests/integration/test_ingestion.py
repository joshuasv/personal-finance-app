"""Integration tests for the ingestion pipeline and review flow."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from finance.core.models import (
    DraftStatus,
    DraftTransaction,
    IngestionBatch,
    Transaction,
)
from finance.core.services import (
    CurrencyMismatchError,
    create_account,
    record_transaction,
)
from finance.core.services.transactions import DuplicateTransactionError
from finance.ingestion import (
    AdapterParseError,
    AdapterRegistry,
    WiseStatementAdapter,
    build_default_adapter_registry,
)
from finance.ingestion.pipeline import (
    AdapterNotFoundError,
    DuplicateBatchError,
    import_artifact,
)
from finance.ingestion.review import (
    DraftNotFoundError,
    DraftNotPendingError,
    confirm_draft,
    reject_draft,
)

pytestmark = pytest.mark.integration


FIXTURE_PDF = Path(__file__).parent.parent / "fixtures" / "wise" / "april_2026.pdf"


@pytest.fixture
def fixture_pdf(tmp_path: Path) -> Path:
    """Copy the bundled Wise PDF into a tmp dir so tests don't share inode state."""
    dst = tmp_path / "april_2026.pdf"
    shutil.copy2(FIXTURE_PDF, dst)
    return dst


@pytest.fixture
def adapter_registry() -> AdapterRegistry:
    return build_default_adapter_registry()


def _make_eur_account(session: Session, name: str = "Wise EUR"):
    return create_account(session, name=name, currency="EUR")


def test_default_registry_contains_wise_pdf() -> None:
    registry = build_default_adapter_registry()
    ids = [a.id for a in registry.list_adapters()]
    assert "wise-pdf" in ids
    adapter = registry.get_adapter("wise-pdf")
    assert adapter.display_name == "Wise (PDF statement)"


def test_import_artifact_creates_batch_and_drafts(
    db_session: Session, adapter_registry: AdapterRegistry, fixture_pdf: Path
) -> None:
    account = _make_eur_account(db_session)
    result = import_artifact(
        db_session,
        adapter_id="wise-pdf",
        path=fixture_pdf,
        account_id=account.id,
        registry=adapter_registry,
    )

    assert result.adapter_id == "wise-pdf"
    assert result.account_id == account.id
    assert result.draft_count > 0
    assert result.duplicates_skipped == 0
    assert len(result.source_sha256) == 64
    assert result.source_filename == "april_2026.pdf"
    assert result.source_size_bytes > 0

    batch = db_session.get(IngestionBatch, result.batch_id)
    assert batch is not None
    assert batch.draft_count == result.draft_count

    drafts = (
        db_session.query(DraftTransaction)
        .filter(DraftTransaction.batch_id == result.batch_id)
        .all()
    )
    assert len(drafts) == result.draft_count
    assert all(d.status is DraftStatus.pending for d in drafts)
    assert all(d.currency == "EUR" for d in drafts)


def test_drafts_do_not_affect_balance(
    db_session: Session, adapter_registry: AdapterRegistry, fixture_pdf: Path
) -> None:
    from finance.core.services import account_balance

    account = _make_eur_account(db_session)
    before = account_balance(db_session, account_id=account.id).minor
    import_artifact(
        db_session,
        adapter_id="wise-pdf",
        path=fixture_pdf,
        account_id=account.id,
        registry=adapter_registry,
    )
    after = account_balance(db_session, account_id=account.id).minor
    assert before == after == 0


def test_unknown_adapter_raises(
    db_session: Session, adapter_registry: AdapterRegistry, fixture_pdf: Path
) -> None:
    account = _make_eur_account(db_session)
    with pytest.raises(AdapterNotFoundError, match="madeup"):
        import_artifact(
            db_session,
            adapter_id="madeup",
            path=fixture_pdf,
            account_id=account.id,
            registry=adapter_registry,
        )


def test_currency_mismatch_aborts_without_writes(
    db_session: Session, adapter_registry: AdapterRegistry, fixture_pdf: Path
) -> None:
    account = create_account(db_session, name="Wise GBP", currency="GBP")
    with pytest.raises(CurrencyMismatchError, match="EUR"):
        import_artifact(
            db_session,
            adapter_id="wise-pdf",
            path=fixture_pdf,
            account_id=account.id,
            registry=adapter_registry,
        )
    # No batch persisted on failure (the parse-time exception aborts the
    # caller's flush; under the test session_scope this rolls back).
    assert db_session.query(IngestionBatch).count() == 0
    assert db_session.query(DraftTransaction).count() == 0


def test_duplicate_batch_refused_without_force(
    db_session: Session, adapter_registry: AdapterRegistry, fixture_pdf: Path
) -> None:
    account = _make_eur_account(db_session)
    import_artifact(
        db_session,
        adapter_id="wise-pdf",
        path=fixture_pdf,
        account_id=account.id,
        registry=adapter_registry,
    )
    db_session.commit()
    with pytest.raises(DuplicateBatchError):
        import_artifact(
            db_session,
            adapter_id="wise-pdf",
            path=fixture_pdf,
            account_id=account.id,
            registry=adapter_registry,
        )


def test_duplicate_batch_allowed_with_force(
    db_session: Session, adapter_registry: AdapterRegistry, fixture_pdf: Path
) -> None:
    account = _make_eur_account(db_session)
    first = import_artifact(
        db_session,
        adapter_id="wise-pdf",
        path=fixture_pdf,
        account_id=account.id,
        registry=adapter_registry,
    )
    db_session.commit()
    second = import_artifact(
        db_session,
        adapter_id="wise-pdf",
        path=fixture_pdf,
        account_id=account.id,
        registry=adapter_registry,
        force=True,
    )
    assert second.batch_id != first.batch_id
    assert second.source_sha256 == first.source_sha256


def test_parser_failure_surfaces_adapter_id(db_session: Session, tmp_path: Path) -> None:
    not_pdf = tmp_path / "not-a-pdf.txt"
    not_pdf.write_text("This is not a PDF.")
    adapter = WiseStatementAdapter()
    with pytest.raises(AdapterParseError) as exc_info:
        list(adapter.parse(not_pdf))
    assert "wise-pdf" in str(exc_info.value)


def test_parser_failure_on_non_wise_pdf(db_session: Session, tmp_path: Path) -> None:
    """A real PDF that isn't a Wise statement should fail with a clear error."""
    fake = tmp_path / "not_wise.pdf"
    # Minimal valid PDF (single page, "Hello world", no Wise header).
    fake.write_bytes(_MINIMAL_PDF)
    adapter = WiseStatementAdapter()
    with pytest.raises(AdapterParseError) as exc_info:
        list(adapter.parse(fake))
    msg = str(exc_info.value)
    assert "wise-pdf" in msg
    assert "page 1" in msg


def test_confirm_draft_creates_transaction(
    db_session: Session, adapter_registry: AdapterRegistry, fixture_pdf: Path
) -> None:
    account = _make_eur_account(db_session)
    result = import_artifact(
        db_session,
        adapter_id="wise-pdf",
        path=fixture_pdf,
        account_id=account.id,
        registry=adapter_registry,
    )
    drafts = (
        db_session.query(DraftTransaction)
        .filter(DraftTransaction.batch_id == result.batch_id)
        .order_by(DraftTransaction.id)
        .all()
    )
    target = drafts[0]
    tx = confirm_draft(db_session, draft_id=target.id)

    assert tx.account_id == account.id
    assert tx.amount_minor == target.amount_minor
    assert tx.posted_date == target.posted_date
    assert tx.payee == target.payee
    assert tx.entered_by == "imported:wise-pdf"

    db_session.refresh(target)
    assert target.status is DraftStatus.confirmed
    assert target.confirmed_transaction_id == tx.id


def test_confirm_draft_idempotent_failure(
    db_session: Session, adapter_registry: AdapterRegistry, fixture_pdf: Path
) -> None:
    account = _make_eur_account(db_session)
    result = import_artifact(
        db_session,
        adapter_id="wise-pdf",
        path=fixture_pdf,
        account_id=account.id,
        registry=adapter_registry,
    )
    target = (
        db_session.query(DraftTransaction)
        .filter(DraftTransaction.batch_id == result.batch_id)
        .order_by(DraftTransaction.id)
        .first()
    )
    confirm_draft(db_session, draft_id=target.id)
    with pytest.raises(DraftNotPendingError):
        confirm_draft(db_session, draft_id=target.id)


def test_reject_draft_marks_rejected_no_transaction(
    db_session: Session, adapter_registry: AdapterRegistry, fixture_pdf: Path
) -> None:
    account = _make_eur_account(db_session)
    result = import_artifact(
        db_session,
        adapter_id="wise-pdf",
        path=fixture_pdf,
        account_id=account.id,
        registry=adapter_registry,
    )
    target = (
        db_session.query(DraftTransaction)
        .filter(DraftTransaction.batch_id == result.batch_id)
        .order_by(DraftTransaction.id)
        .first()
    )
    before_tx = db_session.query(Transaction).count()
    reject_draft(db_session, draft_id=target.id)
    after_tx = db_session.query(Transaction).count()

    db_session.refresh(target)
    assert target.status is DraftStatus.rejected
    assert before_tx == after_tx


def test_reject_then_reject_fails(
    db_session: Session, adapter_registry: AdapterRegistry, fixture_pdf: Path
) -> None:
    account = _make_eur_account(db_session)
    result = import_artifact(
        db_session,
        adapter_id="wise-pdf",
        path=fixture_pdf,
        account_id=account.id,
        registry=adapter_registry,
    )
    target = (
        db_session.query(DraftTransaction)
        .filter(DraftTransaction.batch_id == result.batch_id)
        .order_by(DraftTransaction.id)
        .first()
    )
    reject_draft(db_session, draft_id=target.id)
    with pytest.raises(DraftNotPendingError):
        reject_draft(db_session, draft_id=target.id)


def test_confirm_refuses_when_manual_duplicate_exists(
    db_session: Session, adapter_registry: AdapterRegistry, fixture_pdf: Path
) -> None:
    """Confirming a draft whose content hash already exists on the canonical
    ledger fails and leaves the draft pending."""
    account = _make_eur_account(db_session)
    result = import_artifact(
        db_session,
        adapter_id="wise-pdf",
        path=fixture_pdf,
        account_id=account.id,
        registry=adapter_registry,
    )
    target = (
        db_session.query(DraftTransaction)
        .filter(DraftTransaction.batch_id == result.batch_id)
        .order_by(DraftTransaction.id)
        .first()
    )

    # Manually pre-record a transaction with the same fields.
    record_transaction(
        db_session,
        account_id=account.id,
        posted_date=target.posted_date,
        amount_minor=target.amount_minor,
        currency=account.currency,
        payee=target.payee,
        memo=target.memo,
    )
    with pytest.raises(DuplicateTransactionError):
        confirm_draft(db_session, draft_id=target.id)
    db_session.refresh(target)
    assert target.status is DraftStatus.pending


def test_confirm_unknown_draft_raises(db_session: Session) -> None:
    with pytest.raises(DraftNotFoundError):
        confirm_draft(db_session, draft_id=99999)


def test_reject_unknown_draft_raises(db_session: Session) -> None:
    with pytest.raises(DraftNotFoundError):
        reject_draft(db_session, draft_id=99999)


# A minimal valid PDF containing the literal text "Hello world." on one page.
# Built and verified by hand; pdfplumber accepts it but it has no Wise header
# so the adapter should fail with a clear page-1 error.
_MINIMAL_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
    b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]"
    b" /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
    b"4 0 obj\n<< /Length 44 >>\nstream\n"
    b"BT /F1 12 Tf 100 700 Td (Hello world.) Tj ET\n"
    b"endstream\nendobj\n"
    b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
    b"xref\n0 6\n"
    b"0000000000 65535 f \n"
    b"0000000010 00000 n \n"
    b"0000000060 00000 n \n"
    b"0000000111 00000 n \n"
    b"0000000228 00000 n \n"
    b"0000000316 00000 n \n"
    b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n382\n%%EOF\n"
)
