"""add-bill-is-notified-column

Revision ID: ca5a1f05744d
Revises: c3a1f5e8d9b2
Create Date: 2026-04-03 07:48:00.460979

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ca5a1f05744d"
down_revision: str | Sequence[str] | None = "c3a1f5e8d9b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add is_notified with server_default=True so existing bills are marked as notified
    op.add_column(
        "bills",
        sa.Column(
            "is_notified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("bills", "is_notified")
    # ### end Alembic commands ###
