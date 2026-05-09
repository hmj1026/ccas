"""add-transaction-user-fields

Revision ID: a4b8c2d6e0f1
Revises: 0a2c400f1179
Create Date: 2026-05-08 21:50:00.000000

bills-management-and-insights §1.1, §1.5：為 ``transactions`` 表新增使用者
編輯欄位（manual_category_override / tags / merchant_alias / updated_at）並
建立 (category, trans_date) 複合索引以加速 insights 查詢。

**Spec deviation**：spec 寫 (category_id, transaction_date) 索引，但既有
schema 為 ``category Text`` 與 ``trans_date Date``，無 category_id FK；改為
等價的 (category, trans_date) 複合索引，符合 spec 精神（為月對比 / 分類
group by 查詢加速）。

注意 SQLite ALTER TABLE ADD COLUMN 必須提供常數 server_default 才能對既有
row 回填；對 ``DateTime`` 欄位使用 ``CURRENT_TIMESTAMP`` 子句。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a4b8c2d6e0f1"
down_revision: str | Sequence[str] | None = "0a2c400f1179"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column(
            "manual_category_override",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "transactions",
        sa.Column(
            "tags",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )
    op.add_column(
        "transactions",
        sa.Column(
            "merchant_alias",
            sa.Text(),
            nullable=False,
            server_default="",
        ),
    )
    op.add_column(
        "transactions",
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )

    op.create_index(
        "ix_transactions_category_trans_date",
        "transactions",
        ["category", "trans_date"],
    )

    # SQLite trigger 確保 updated_at 在 Core-style bulk UPDATE 下亦自動刷新
    # （與 bank_settings / pipeline_runs 同 pattern）。
    op.execute(
        """
        CREATE TRIGGER transactions_updated_at_trigger
        AFTER UPDATE ON transactions
        FOR EACH ROW
        WHEN NEW.updated_at = OLD.updated_at
        BEGIN
          UPDATE transactions
            SET updated_at = CURRENT_TIMESTAMP
            WHERE id = NEW.id;
        END;
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS transactions_updated_at_trigger")
    op.drop_index("ix_transactions_category_trans_date", table_name="transactions")
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.drop_column("updated_at")
        batch_op.drop_column("merchant_alias")
        batch_op.drop_column("tags")
        batch_op.drop_column("manual_category_override")
