"""add-category-source

Revision ID: 066eb5d1c70c
Revises: 1334f4fe5f73
Create Date: 2026-04-12 09:35:52.815897

Adds a ``source`` column to ``categories`` to distinguish seed rows
(written by ``ccas.tools.categories`` from YAML) from user-created rows.
Existing rows default to ``"user"`` so the first reseed after this
migration never deletes rows whose provenance is unknown — only rows
explicitly rewritten by the seed tool become ``"seed"`` and thus
eligible for later orphan cleanup.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "066eb5d1c70c"
down_revision: str | Sequence[str] | None = "1334f4fe5f73"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "categories",
        sa.Column(
            "source",
            sa.Text(),
            server_default="user",
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("categories", "source")
