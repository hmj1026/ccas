"""add payment_reminders table

Revision ID: c3a1f5e8d9b2
Revises: 08828cd4e8ca
Create Date: 2026-03-31 15:45:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c3a1f5e8d9b2'
down_revision: str | Sequence[str] | None = '08828cd4e8ca'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'payment_reminders',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('bill_id', sa.Integer(), nullable=False),
        sa.Column('reminder_type', sa.Text(), nullable=False),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['bill_id'], ['bills.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('bill_id', 'reminder_type', name='uq_reminder_bill_type'),
    )


def downgrade() -> None:
    op.drop_table('payment_reminders')
