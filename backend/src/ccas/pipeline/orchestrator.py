"""五階段 pipeline 協調器。

依序執行 ingest -> decrypt -> parse -> classify -> notify，
每階段部分失敗不阻斷後續階段。
"""

from __future__ import annotations

import logging
import time

from sqlalchemy.ext.asyncio import AsyncSession

from ccas.bot.job import NotifySummary, run_notify_job
from ccas.classifier.job import ClassifySummary, run_classify_job
from ccas.decryptor.job import DecryptionSummary, run_decryption_job
from ccas.ingestor.job import IngestionSummary, run_ingestion_job
from ccas.parser.job import ParseSummary, run_parse_job
from ccas.pipeline.options import PipelineOptions
from ccas.pipeline.summary import FailedItem, PipelineSummary, StageSummary

logger = logging.getLogger(__name__)

STAGE_ORDER: tuple[str, ...] = ("ingest", "decrypt", "parse", "classify", "notify")


def _validate_stage_range(
    from_stage: str | None = None,
    to_stage: str | None = None,
) -> tuple[str, ...]:
    """Validate from/to stage names and return the stages to execute.

    Args:
        from_stage: Start stage (inclusive). None means first stage.
        to_stage: End stage (inclusive). None means last stage.

    Returns:
        Tuple of stage names to execute, in order.

    Raises:
        ValueError: If stage names are invalid or from_stage is after to_stage.
    """
    valid_names = ", ".join(STAGE_ORDER)

    from_idx = 0
    if from_stage is not None:
        if from_stage not in STAGE_ORDER:
            raise ValueError(f"無效的階段名稱: '{from_stage}'。有效名稱: {valid_names}")
        from_idx = STAGE_ORDER.index(from_stage)

    to_idx = len(STAGE_ORDER) - 1
    if to_stage is not None:
        if to_stage not in STAGE_ORDER:
            raise ValueError(f"無效的階段名稱: '{to_stage}'。有效名稱: {valid_names}")
        to_idx = STAGE_ORDER.index(to_stage)

    if from_idx > to_idx:
        raise ValueError(
            f"from_stage '{from_stage}' 必須在 to_stage '{to_stage}' 之前或相同"
        )

    return STAGE_ORDER[from_idx : to_idx + 1]


def _ingest_stage_summary(s: IngestionSummary) -> StageSummary:
    return StageSummary(
        stage="ingest",
        counts={
            "staged": s.staged_count,
            "skipped": s.skipped_count,
            "failed": s.failed_count,
        },
        errors=list(s.errors),
    )


def _decrypt_stage_summary(s: DecryptionSummary) -> StageSummary:
    return StageSummary(
        stage="decrypt",
        counts={
            "decrypted": s.decrypted_count,
            "passthrough": s.passthrough_count,
            "failed": s.failed_count,
        },
        errors=list(s.errors),
    )


def _parse_stage_summary(s: ParseSummary) -> StageSummary:
    return StageSummary(
        stage="parse",
        counts={
            "parsed": s.parsed_count,
            "skipped": s.skipped_count,
            "failed": s.failed_count,
        },
        errors=list(s.errors),
    )


def _classify_stage_summary(s: ClassifySummary) -> StageSummary:
    return StageSummary(
        stage="classify",
        counts={"classified": s.classified_count},
    )


def _notify_stage_summary(s: NotifySummary) -> StageSummary:
    return StageSummary(
        stage="notify",
        counts={
            "sent": s.sent_count,
            "failed": s.failed_count,
        },
        errors=list(s.errors),
    )


def _collect_failures(*stage_summaries: StageSummary) -> tuple[FailedItem, ...]:
    """從所有階段的 errors 中收集失敗項目。"""
    items: list[FailedItem] = []
    for ss in stage_summaries:
        for i, error in enumerate(ss.errors):
            items.append(FailedItem(item_id=f"{ss.stage}:{i}", error=error))
    return tuple(items)


async def _run_stage(
    stage_name: str,
    session: AsyncSession,
    options: PipelineOptions | None,
    stage_num: int,
    total_stages: int,
) -> StageSummary:
    """Execute a single pipeline stage and return its summary."""
    logger.info("Pipeline stage %d/%d: %s", stage_num, total_stages, stage_name)

    if stage_name == "ingest":
        result = await run_ingestion_job(session, options)
        return _ingest_stage_summary(result)
    if stage_name == "decrypt":
        result = await run_decryption_job(session, options)
        return _decrypt_stage_summary(result)
    if stage_name == "parse":
        result = await run_parse_job(session, options)
        return _parse_stage_summary(result)
    if stage_name == "classify":
        result = await run_classify_job(session)
        return _classify_stage_summary(result)
    # notify
    result = await run_notify_job(session)
    return _notify_stage_summary(result)


async def run_pipeline(
    session: AsyncSession,
    options: PipelineOptions | None = None,
) -> PipelineSummary:
    """執行 pipeline 並回傳結構化摘要。

    根據 options.from_stage / to_stage 決定執行範圍，
    預設執行全部五階段：ingest -> decrypt -> parse -> classify -> notify。
    每階段部分失敗不阻斷後續階段。

    Args:
        session: 非同步 DB Session。
        options: Pipeline 執行參數（可選）。

    Returns:
        PipelineSummary 包含各階段統計與總耗時。
    """
    from_stage = options.from_stage if options else None
    to_stage = options.to_stage if options else None
    stages_to_run = _validate_stage_range(from_stage, to_stage)

    start = time.monotonic()

    stage_summaries: list[StageSummary] = []
    for i, stage_name in enumerate(stages_to_run, 1):
        ss = await _run_stage(stage_name, session, options, i, len(stages_to_run))
        stage_summaries.append(ss)

    elapsed = time.monotonic() - start
    failures = _collect_failures(*stage_summaries)

    summary = PipelineSummary(
        stages=tuple(stage_summaries),
        total_seconds=round(elapsed, 2),
        failures=failures,
    )

    counts_str = " ".join(
        f"{ss.stage}={sum(ss.counts.values())}" for ss in stage_summaries
    )
    logger.info("Pipeline completed in %.2fs: %s", elapsed, counts_str)

    return summary
