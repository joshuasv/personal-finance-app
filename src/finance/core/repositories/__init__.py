"""Pure-CRUD repositories over the SQLAlchemy session.

Repositories know nothing about validation, invariants, or operation models;
those live in `core.services`. A repository's only job is to translate between
domain concepts and SQL.
"""

from finance.core.repositories.accounts import AccountRepository
from finance.core.repositories.transactions import TransactionRepository

__all__ = ["AccountRepository", "TransactionRepository"]
