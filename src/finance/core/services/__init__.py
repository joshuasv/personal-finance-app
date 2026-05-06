"""Service layer: enforce invariants on top of repositories.

Each public function is a single domain operation. Services raise typed errors
that the operation/registry layer maps to API/CLI errors.
"""

from finance.core.services.accounts import (
    AccountInUseError,
    AccountNotFoundError,
    DuplicateAccountNameError,
    archive_account,
    create_account,
    list_accounts,
)
from finance.core.services.balances import account_balance
from finance.core.services.errors import (
    AccountArchivedError,
    AmountZeroError,
    CurrencyMismatchError,
    DomainError,
    NotFoundError,
    ValidationError,
)
from finance.core.services.transactions import (
    DuplicateTransactionError,
    TransactionNotFoundError,
    delete_transaction,
    list_transactions,
    record_transaction,
    update_transaction,
)

__all__ = [
    "AccountArchivedError",
    "AccountInUseError",
    "AccountNotFoundError",
    "AmountZeroError",
    "CurrencyMismatchError",
    "DomainError",
    "DuplicateAccountNameError",
    "DuplicateTransactionError",
    "NotFoundError",
    "TransactionNotFoundError",
    "ValidationError",
    "account_balance",
    "archive_account",
    "create_account",
    "delete_transaction",
    "list_accounts",
    "list_transactions",
    "record_transaction",
    "update_transaction",
]
