"""add notified to budget_alerts

Revision ID: 413739f494ff
Revises: a344841591e6
Create Date: 2026-06-21 14:19:40.752653

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "413739f494ff"
down_revision: str | Sequence[str] | None = "a344841591e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema.

    僅新增 ``budget_alerts.notified`` 欄位。autogenerate 對既有 expression
    index（``triggered_at DESC`` 等）產生的 drop/create 為近似簽名誤判
    （SQLite 表達式索引限制），以及 ``payment_reminders.sent_at`` 的 NOT NULL
    皆與本變更無關，已移除。
    """
    op.add_column(
        "budget_alerts",
        sa.Column(
            "notified",
            sa.Boolean(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("budget_alerts", "notified")
