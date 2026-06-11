"""add-missing-indexes

Revision ID: ec74b5138c9f
Revises: 9b3e2c8a4f10
Create Date: 2026-06-10 00:00:00.000000

db-missing-indexes（P1 效能）：補上熱路徑查詢缺少的索引。

- ``ix_transactions_bill_id``: FK join / 帳單明細查詢
- ``ix_payment_reminders_bill_id``: FK join / 提醒去重查詢
- ``ix_staged_attachments_status``: pipeline 各階段以 status 撈 staging 列
- ``ix_bills_billing_month``: 月份篩選 / 統計查詢
- ``ix_bills_is_notified_false``: partial index，notify 階段只掃未通知帳單
- ``ix_bills_is_paid_false``: partial index，提醒排程只掃未繳款帳單
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ec74b5138c9f"
down_revision: str | Sequence[str] | None = "9b3e2c8a4f10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_transactions_bill_id", "transactions", ["bill_id"])
    op.create_index("ix_payment_reminders_bill_id", "payment_reminders", ["bill_id"])
    op.create_index("ix_staged_attachments_status", "staged_attachments", ["status"])
    op.create_index("ix_bills_billing_month", "bills", ["billing_month"])
    op.create_index(
        "ix_bills_is_notified_false",
        "bills",
        ["is_notified"],
        sqlite_where=sa.text("is_notified = 0"),
    )
    op.create_index(
        "ix_bills_is_paid_false",
        "bills",
        ["is_paid"],
        sqlite_where=sa.text("is_paid = 0"),
    )


def downgrade() -> None:
    op.drop_index("ix_bills_is_paid_false", table_name="bills")
    op.drop_index("ix_bills_is_notified_false", table_name="bills")
    op.drop_index("ix_bills_billing_month", table_name="bills")
    op.drop_index("ix_staged_attachments_status", table_name="staged_attachments")
    op.drop_index("ix_payment_reminders_bill_id", table_name="payment_reminders")
    op.drop_index("ix_transactions_bill_id", table_name="transactions")
