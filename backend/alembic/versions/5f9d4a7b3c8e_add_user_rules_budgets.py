"""add-user-rules-budgets

Revision ID: 5f9d4a7b3c8e
Revises: a4b8c2d6e0f1
Create Date: 2026-05-08 21:51:00.000000

bills-management-and-insights §1.2-§1.4, §1.6：建立 ``classification_rules`` /
``budgets`` / ``budget_alerts`` 三張表，含對應索引與 SQLite triggers
（updated_at bulk update 自動刷新）。

- ``classification_rules``：使用者自訂進階分類規則（pattern + pattern_type +
  category FK + priority + enabled）
- ``budgets``：預算上限與警示閾值（scope + scope_ref + amount + threshold）
- ``budget_alerts``：超支警示記錄（同月同 budget 同 threshold 不重複）

索引：
- ``ix_classification_rules_priority_enabled``: ``priority DESC, enabled``
  支援優先序排序 + active filter
- ``ix_budgets_scope_ref``: ``(scope, scope_ref)`` 支援 evaluator 查詢
- ``ix_budget_alerts_triggered_at_desc``: ``triggered_at DESC`` 支援 active
  alert 查詢
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5f9d4a7b3c8e"
down_revision: str | Sequence[str] | None = "a4b8c2d6e0f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "classification_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("pattern", sa.Text(), nullable=False),
        sa.Column("pattern_type", sa.String(length=16), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    # priority DESC + enabled — expression-based, autogen 反射不出，手寫 SQL
    op.execute(
        "CREATE INDEX ix_classification_rules_priority_enabled "
        "ON classification_rules (priority DESC, enabled)"
    )

    op.create_table(
        "budgets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column("scope_ref", sa.Text(), nullable=True),
        sa.Column("amount_minor_units", sa.Integer(), nullable=False),
        sa.Column(
            "alert_threshold_percent",
            sa.Integer(),
            nullable=False,
            server_default="80",
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_budgets_scope_ref", "budgets", ["scope", "scope_ref"])

    op.create_table(
        "budget_alerts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("budget_id", sa.Integer(), nullable=False),
        sa.Column("period_year_month", sa.String(length=7), nullable=False),
        sa.Column("threshold_breached_percent", sa.Integer(), nullable=False),
        sa.Column("current_amount_minor_units", sa.Integer(), nullable=False),
        sa.Column("triggered_at", sa.DateTime(), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["budget_id"], ["budgets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        "CREATE INDEX ix_budget_alerts_triggered_at_desc "
        "ON budget_alerts (triggered_at DESC)"
    )

    # SQLite triggers — 同 bank_settings / transactions pattern。
    op.execute(
        """
        CREATE TRIGGER classification_rules_updated_at_trigger
        AFTER UPDATE ON classification_rules
        FOR EACH ROW
        WHEN NEW.updated_at = OLD.updated_at
        BEGIN
          UPDATE classification_rules
            SET updated_at = CURRENT_TIMESTAMP
            WHERE id = NEW.id;
        END;
        """
    )
    op.execute(
        """
        CREATE TRIGGER budgets_updated_at_trigger
        AFTER UPDATE ON budgets
        FOR EACH ROW
        WHEN NEW.updated_at = OLD.updated_at
        BEGIN
          UPDATE budgets
            SET updated_at = CURRENT_TIMESTAMP
            WHERE id = NEW.id;
        END;
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS budgets_updated_at_trigger")
    op.execute("DROP TRIGGER IF EXISTS classification_rules_updated_at_trigger")
    op.execute("DROP INDEX IF EXISTS ix_budget_alerts_triggered_at_desc")
    op.drop_table("budget_alerts")
    op.drop_index("ix_budgets_scope_ref", table_name="budgets")
    op.drop_table("budgets")
    op.execute("DROP INDEX IF EXISTS ix_classification_rules_priority_enabled")
    op.drop_table("classification_rules")
