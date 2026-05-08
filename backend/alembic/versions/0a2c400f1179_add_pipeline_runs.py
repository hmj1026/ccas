"""add-pipeline-runs

Revision ID: 0a2c400f1179
Revises: 2570bbdebf54
Create Date: 2026-05-05 00:00:00.000000

pipeline-operations-center §1.3：建立 ``pipeline_runs`` 表作為 pipeline
執行歷史與即時進度 SSOT。本 migration 僅新增表，不修改既有表結構，
downgrade 為 drop trigger + drop indexes + drop table，無破壞性。

索引設計（spec §1.3 / D5）：
- ``ix_pipeline_runs_created_at_desc``：list query 命中 ``ORDER BY created_at DESC``
- ``ix_pipeline_runs_status``：active run filter（``WHERE status='running'``）

SQLite trigger：``updated_at`` 在 Core-style bulk UPDATE 下亦自動刷新
（DbProgressReporter 走 single UPDATE，需 trigger 才能準確記錄最後寫入時間）。
與 oauth-onboarding-ui ``2570bbdebf54`` ``bank_settings`` 同 pattern。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0a2c400f1179"
down_revision: str | Sequence[str] | None = "2570bbdebf54"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("job_id", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="queued",
        ),
        sa.Column("triggered_by", sa.String(length=32), nullable=False),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("current_stage", sa.String(length=16), nullable=True),
        sa.Column(
            "current_stage_processed",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "current_stage_total",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("stage_summary", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        "CREATE INDEX ix_pipeline_runs_created_at_desc "
        "ON pipeline_runs (created_at DESC)"
    )
    op.create_index(
        "ix_pipeline_runs_status",
        "pipeline_runs",
        ["status"],
    )

    op.execute(
        """
        CREATE TRIGGER pipeline_runs_updated_at_trigger
        AFTER UPDATE ON pipeline_runs
        FOR EACH ROW
        WHEN NEW.updated_at = OLD.updated_at
        BEGIN
          UPDATE pipeline_runs
            SET updated_at = CURRENT_TIMESTAMP
            WHERE id = NEW.id;
        END;
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS pipeline_runs_updated_at_trigger")
    op.drop_index("ix_pipeline_runs_status", table_name="pipeline_runs")
    op.execute("DROP INDEX IF EXISTS ix_pipeline_runs_created_at_desc")
    op.drop_table("pipeline_runs")
