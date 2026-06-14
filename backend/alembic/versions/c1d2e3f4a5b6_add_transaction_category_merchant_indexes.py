"""add-transaction-merchant-index

Revision ID: c1d2e3f4a5b6
Revises: f3a9d8c1b2e4
Create Date: 2026-06-14 00:00:00.000000

效能（R29）：transactions.merchant 先前無索引，top-merchants 的
GROUP BY merchant 與商家篩選退化為全表掃描。補上 ``ix_transactions_merchant``。

註：``ix_transactions_category_trans_date``（R27）已由 a4b8c2d6e0f1 建立，
此處不重建；R27 僅需在 model ``__table_args__`` 補回同名宣告以消除
autogenerate drift（model 與 DB 不再分歧）。
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c1d2e3f4a5b6"
down_revision: str | Sequence[str] | None = "f3a9d8c1b2e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_transactions_merchant",
        "transactions",
        ["merchant"],
    )


def downgrade() -> None:
    op.drop_index("ix_transactions_merchant", table_name="transactions")
