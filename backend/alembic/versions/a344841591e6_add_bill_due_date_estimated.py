"""add bill.due_date_estimated

Revision ID: a344841591e6
Revises: 65070f49fd2d
Create Date: 2026-06-16 08:32:27.446652

ctbc-due-date-estimate-flag（P2 觀測）：CTBC 兩頁帳單在缺乏精確繳費截止日時，
退而估算為當月 28 日。新增內部觀測欄位 ``bills.due_date_estimated``（不對外
暴露於任何 API/前端 schema），標記該 ``due_date`` 為估算值，供提醒邏輯放寬
比對窗使用。以 server_default 0 backfill 既有 row（皆視為非估算）。

說明：autogenerate 會額外偵測到 SQLite expression index（如
``ix_pipeline_runs_created_at_desc``）與 ``payment_reminders.sent_at`` 的
近似簽章 diff，皆為既有 schema 與 SQLite 無法 round-trip expression index 的
已知雜訊，與本次變更無關，故本 migration 僅保留欄位新增。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a344841591e6"
down_revision: str | Sequence[str] | None = "65070f49fd2d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "bills",
        sa.Column(
            "due_date_estimated",
            sa.Boolean(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("bills", "due_date_estimated")
