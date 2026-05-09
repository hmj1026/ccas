"""add-setup-tables

Revision ID: 2570bbdebf54
Revises: 066eb5d1c70c
Create Date: 2026-05-02 12:02:16.779552

oauth-onboarding-ui §2.4：建立 bank_settings、bank_secrets、gmail_oauth_state
三張表，作為 setup UX backend SSOT（取代手動編輯 banks.yaml / .env 的 PDF
密碼 / Gmail CLI flow）。三張表彼此獨立，無外鍵；bank_code 由 service 層
負責一致性（與 banks.yaml 對齊）。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2570bbdebf54"
down_revision: str | Sequence[str] | None = "066eb5d1c70c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bank_settings",
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("display_name", sa.String(length=128), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("code"),
    )
    op.create_table(
        "bank_secrets",
        sa.Column("bank_code", sa.String(length=32), nullable=False),
        sa.Column("encrypted_password", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("bank_code"),
    )
    op.create_table(
        "gmail_oauth_state",
        sa.Column("state", sa.String(length=128), nullable=False),
        sa.Column("code_verifier", sa.String(length=256), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("state"),
    )

    # SQLite triggers to keep updated_at fresh under bulk UPDATE statements.
    # SQLAlchemy's ``onupdate=`` only fires on ORM-tracked instance attribute
    # changes; Core-style ``update().where()`` bypasses it silently. The
    # triggers below guarantee the timestamp moves forward regardless of
    # writer style. ``WHEN NEW.updated_at = OLD.updated_at`` avoids infinite
    # recursion when an explicit ORM update already sets the column.
    op.execute(
        """
        CREATE TRIGGER bank_settings_updated_at_trigger
        AFTER UPDATE ON bank_settings
        FOR EACH ROW
        WHEN NEW.updated_at = OLD.updated_at
        BEGIN
          UPDATE bank_settings
            SET updated_at = CURRENT_TIMESTAMP
            WHERE code = NEW.code;
        END;
        """
    )
    op.execute(
        """
        CREATE TRIGGER bank_secrets_updated_at_trigger
        AFTER UPDATE ON bank_secrets
        FOR EACH ROW
        WHEN NEW.updated_at = OLD.updated_at
        BEGIN
          UPDATE bank_secrets
            SET updated_at = CURRENT_TIMESTAMP
            WHERE bank_code = NEW.bank_code;
        END;
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS bank_secrets_updated_at_trigger")
    op.execute("DROP TRIGGER IF EXISTS bank_settings_updated_at_trigger")
    op.drop_table("gmail_oauth_state")
    op.drop_table("bank_secrets")
    op.drop_table("bank_settings")
