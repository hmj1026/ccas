"""add-reminder-settings

Revision ID: 9b3e2c8a4f10
Revises: 5f9d4a7b3c8e
Create Date: 2026-05-09 06:50:00.000000

bills-management-and-insights §5：建立 ``reminder_settings`` 表（每張 bill
最多一筆 setting row：enabled / days_before JSON / channel）。

**Spec deviation**：design §D9 假設既有 ``payment_reminders`` 表已含
``(days_before, channel, enabled)``，但實際只有 ``(bill_id, reminder_type,
sent_at)`` (sent log)。為保持 sent log / settings 語意分離，獨立新表
``reminder_settings`` 儲存設定；無 row 時 evaluator 採預設行為
（enabled=true、days_before=[3,1]、channel=telegram），與 change 前等價。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9b3e2c8a4f10"
down_revision: str | Sequence[str] | None = "5f9d4a7b3c8e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reminder_settings",
        sa.Column("bill_id", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column(
            "days_before",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[3, 1]'"),
        ),
        sa.Column(
            "channel",
            sa.String(length=16),
            nullable=False,
            server_default="telegram",
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["bill_id"], ["bills.id"]),
        sa.PrimaryKeyConstraint("bill_id"),
    )

    # SQLite trigger 確保 Core-style bulk UPDATE 也能刷新 updated_at
    op.execute(
        """
        CREATE TRIGGER reminder_settings_updated_at_trigger
        AFTER UPDATE ON reminder_settings
        FOR EACH ROW
        WHEN NEW.updated_at = OLD.updated_at
        BEGIN
          UPDATE reminder_settings
            SET updated_at = CURRENT_TIMESTAMP
            WHERE bill_id = NEW.bill_id;
        END;
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS reminder_settings_updated_at_trigger")
    op.drop_table("reminder_settings")
