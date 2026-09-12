"""add pipeline terminal reason

Revision ID: b72e619af430
Revises: 7f3ae66246a3
Create Date: 2026-09-12 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b72e619af430"
down_revision: str | Sequence[str] | None = "7f3ae66246a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Keep direct re-execution safe for SQLite-based migration tests and
    # operator recovery workflows.  Alembic's version table normally prevents
    # this path, but the revision is also invoked directly by the regression
    # harness and by a few maintenance scripts.
    inspector = sa.inspect(op.get_bind())
    column_names = {column["name"] for column in inspector.get_columns("pipeline_runs")}
    if "terminal_reason" not in column_names:
        op.add_column(
            "pipeline_runs",
            sa.Column("terminal_reason", sa.String(length=32), nullable=True),
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("pipeline_runs", schema=None) as batch_op:
        batch_op.drop_column("terminal_reason")

    # SQLite rebuilds the table for batch operations and therefore drops
    # trigger/index objects that are not represented in the reflected table
    # definition.  Restore the original objects explicitly, including the
    # raw DESC expression used by the pre-existing index.
    op.execute("DROP INDEX IF EXISTS ix_pipeline_runs_created_at_desc")
    op.execute(
        "CREATE INDEX ix_pipeline_runs_created_at_desc "
        "ON pipeline_runs (created_at DESC)"
    )
    op.execute("DROP TRIGGER IF EXISTS pipeline_runs_updated_at_trigger")
    op.execute(
        """
        CREATE TRIGGER pipeline_runs_updated_at_trigger
        AFTER UPDATE ON pipeline_runs
        FOR EACH ROW
        WHEN NEW.updated_at = OLD.updated_at
        BEGIN
          UPDATE pipeline_runs
            SET updated_at = CURRENT_TIMESTAMP
            WHERE id = NEW.id;
        END;
        """
    )
