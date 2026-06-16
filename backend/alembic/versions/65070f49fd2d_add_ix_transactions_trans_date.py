"""add ix_transactions_trans_date

Revision ID: 65070f49fd2d
Revises: c1d2e3f4a5b6
Create Date: 2026-06-16 07:59:56.682959

db-trans-date-index（P3 效能）：交易列表預設 ``ORDER BY trans_date DESC``，
但唯一涵蓋 ``trans_date`` 的索引是複合索引 ``(category, trans_date)``——
缺少 category 篩選時無法用於排序，導致 filesort。補上單欄索引。
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "65070f49fd2d"
down_revision: str | Sequence[str] | None = "c1d2e3f4a5b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_transactions_trans_date", "transactions", ["trans_date"])


def downgrade() -> None:
    op.drop_index("ix_transactions_trans_date", table_name="transactions")
