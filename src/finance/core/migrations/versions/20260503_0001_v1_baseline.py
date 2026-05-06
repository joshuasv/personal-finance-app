"""v1 baseline schema.

Creates the full v1 schema in one shot using the SQLAlchemy metadata. This is
allowed for a baseline migration; subsequent migrations will use explicit
op.* calls.

Revision ID: 0001_v1_baseline
Revises:
Create Date: 2026-05-03
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from finance.core.models import Base

revision: str = "0001_v1_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
