"""add-staged-attachment-gmail-part-id

Revision ID: 1334f4fe5f73
Revises: 11ca9b74b00c
Create Date: 2026-04-10 22:56:56.656041

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1334f4fe5f73"
down_revision: str | Sequence[str] | None = "11ca9b74b00c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add gmail_part_id to staged_attachments and switch dedupe unique key.

    Rationale: Gmail API's ``attachmentId`` is regenerated on every ``messages.get``
    call, so ``(gmail_message_id, gmail_attachment_id)`` is unstable as a dedupe
    key. ``partId`` (MIME tree position) is stable within a message and is used
    going forward. Old rows keep ``gmail_part_id`` NULL; the ingest job falls back
    to filename matching and opportunistically backfills ``gmail_part_id``.
    """
    # Use batch_alter_table for SQLite compatibility when dropping constraints.
    with op.batch_alter_table("staged_attachments", schema=None) as batch_op:
        batch_op.add_column(sa.Column("gmail_part_id", sa.Text(), nullable=True))
        batch_op.drop_constraint("uq_staged_gmail_attachment", type_="unique")
        batch_op.create_unique_constraint(
            "uq_staged_gmail_message_part",
            ["gmail_message_id", "gmail_part_id"],
        )


def downgrade() -> None:
    """Revert gmail_part_id column and restore legacy unique constraint."""
    with op.batch_alter_table("staged_attachments", schema=None) as batch_op:
        batch_op.drop_constraint("uq_staged_gmail_message_part", type_="unique")
        batch_op.create_unique_constraint(
            "uq_staged_gmail_attachment",
            ["gmail_message_id", "gmail_attachment_id"],
        )
        batch_op.drop_column("gmail_part_id")
