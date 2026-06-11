"""rename-budget-amount-columns-to-ntd

Revision ID: f3a9d8c1b2e4
Revises: ec74b5138c9f
Create Date: 2026-06-11 00:00:00.000000

budget-amount-ntd-rename（P2 架構）：修正誤導性欄位命名。

全系統金額以 NTD 整數元儲存，不乘 100；舊名 ``*_minor_units`` 暗示
cents，與實際語意（元）矛盾，僅改名、不轉換數值。

- ``budgets.amount_minor_units`` → ``budgets.amount_ntd``
- ``budget_alerts.current_amount_minor_units`` → ``budget_alerts.current_amount_ntd``
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f3a9d8c1b2e4"
down_revision: str | Sequence[str] | None = "ec74b5138c9f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("budgets") as batch_op:
        batch_op.alter_column(
            "amount_minor_units",
            new_column_name="amount_ntd",
            existing_type=sa.Integer(),
            existing_nullable=False,
        )
    with op.batch_alter_table("budget_alerts") as batch_op:
        batch_op.alter_column(
            "current_amount_minor_units",
            new_column_name="current_amount_ntd",
            existing_type=sa.Integer(),
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("budget_alerts") as batch_op:
        batch_op.alter_column(
            "current_amount_ntd",
            new_column_name="current_amount_minor_units",
            existing_type=sa.Integer(),
            existing_nullable=False,
        )
    with op.batch_alter_table("budgets") as batch_op:
        batch_op.alter_column(
            "amount_ntd",
            new_column_name="amount_minor_units",
            existing_type=sa.Integer(),
            existing_nullable=False,
        )
