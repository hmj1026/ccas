"""add-bank-login-credentials

Revision ID: 7f3ae66246a3
Revises: 413739f494ff
Create Date: 2026-06-21 21:09:11.176504

Note: autogenerate also surfaced approximate-signature diffs for the
expression indexes (ix_budget_alerts_triggered_at_desc,
ix_classification_rules_priority_enabled, ix_pipeline_runs_created_at_desc)
and payment_reminders.sent_at — those are SQLite expression-index
introspection false positives, not real schema drift, and are intentionally
excluded. This migration only adds the new bank_login_credentials table.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7f3ae66246a3"
down_revision: str | Sequence[str] | None = "413739f494ff"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "bank_login_credentials",
        sa.Column("bank_code", sa.String(length=32), nullable=False),
        sa.Column("credential_key", sa.String(length=64), nullable=False),
        sa.Column("encrypted_value", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("bank_code", "credential_key"),
    )
    # Auto-bump updated_at on UPDATE that does not itself touch updated_at
    # (mirrors bank_secrets_updated_at_trigger; composite-PK WHERE clause).
    op.execute(
        """
        CREATE TRIGGER bank_login_credentials_updated_at_trigger
        AFTER UPDATE ON bank_login_credentials
        FOR EACH ROW
        WHEN NEW.updated_at = OLD.updated_at
        BEGIN
          UPDATE bank_login_credentials
            SET updated_at = CURRENT_TIMESTAMP
            WHERE bank_code = NEW.bank_code
              AND credential_key = NEW.credential_key;
        END;
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TRIGGER IF EXISTS bank_login_credentials_updated_at_trigger")
    op.drop_table("bank_login_credentials")
