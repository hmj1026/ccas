"""Shared query filters for pipeline stages.

Applies ``PipelineOptions`` bank_code and date range filters
to ``StagedAttachment`` queries used by decrypt and parse stages.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Select

from ccas.pipeline.options import PipelineOptions
from ccas.storage.models import StagedAttachment


def apply_pipeline_filters(
    stmt: Select[tuple[StagedAttachment]],
    options: PipelineOptions | None,
) -> Select[tuple[StagedAttachment]]:
    """Apply bank_code and date_range filters to a StagedAttachment query.

    Args:
        stmt: Existing SQLAlchemy select statement.
        options: Pipeline options (None means no filtering).

    Returns:
        Filtered select statement.
    """
    if options is None:
        return stmt

    if options.bank_code is not None:
        stmt = stmt.where(StagedAttachment.bank_code == options.bank_code)

    dr = options.date_range()
    if dr is not None:
        start, end = dr
        start_dt = datetime(start.year, start.month, start.day)
        end_dt = datetime(end.year, end.month, end.day)
        stmt = stmt.where(
            StagedAttachment.message_date >= start_dt,
            StagedAttachment.message_date < end_dt,
        )

    return stmt
