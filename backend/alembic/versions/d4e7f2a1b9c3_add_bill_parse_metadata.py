"""add nullable bill parse metadata

Revision ID: d4e7f2a1b9c3
Revises: b72e619af430
Create Date: 2026-09-13 00:00:00.000000

The columns are nullable by design: existing bills have no trustworthy parse
metadata and must not receive inferred values during migration.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d4e7f2a1b9c3"
down_revision: str | Sequence[str] | None = "b72e619af430"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("bills", sa.Column("parse_method", sa.Text(), nullable=True))
    op.add_column("bills", sa.Column("parse_confidence", sa.Float(), nullable=True))
    op.add_column("bills", sa.Column("needs_review", sa.Boolean(), nullable=True))
    op.add_column("bills", sa.Column("review_reasons", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("bills", "review_reasons")
    op.drop_column("bills", "needs_review")
    op.drop_column("bills", "parse_confidence")
    op.drop_column("bills", "parse_method")
