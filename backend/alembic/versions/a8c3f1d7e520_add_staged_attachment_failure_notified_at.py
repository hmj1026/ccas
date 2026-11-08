"""add staged_attachments.failure_notified_at

Revision ID: a8c3f1d7e520
Revises: d4e7f2a1b9c3
Create Date: 2026-11-07 00:00:00.000000

Claim record for the parse-failure notification (ccas.outbox.ParseFailureClaim).
Existing parse_failed attachments are backfilled as already notified so the
first run after upgrade does not announce every historical failure.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a8c3f1d7e520"
down_revision: str | Sequence[str] | None = "d4e7f2a1b9c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "staged_attachments",
        sa.Column("failure_notified_at", sa.DateTime(), nullable=True),
    )
    op.execute(
        "UPDATE staged_attachments SET failure_notified_at = CURRENT_TIMESTAMP "
        "WHERE status = 'parse_failed'"
    )


def downgrade() -> None:
    op.drop_column("staged_attachments", "failure_notified_at")
