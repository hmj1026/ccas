"""add-staged-attachment-source-type

Revision ID: 11ca9b74b00c
Revises: ca5a1f05744d
Create Date: 2026-04-09 10:21:37.980382

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "11ca9b74b00c"
down_revision: str | Sequence[str] | None = "ca5a1f05744d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "staged_attachments",
        sa.Column(
            "source_type",
            sa.Text(),
            server_default="attachment",
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("staged_attachments", "source_type")
