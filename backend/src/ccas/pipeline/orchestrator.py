"""五階段 pipeline 協調器。

依序執行 ingest -> decrypt -> parse -> classify -> notify，
每階段部分失敗不阻斷後續階段。
"""

import logging
import time

from sqlalchemy.ext.asyncio import AsyncSession

from ccas.bot.job import NotifySummary, run_notify_job
from ccas.classifier.job import ClassifySummary, run_classify_job
from ccas.decryptor.job import DecryptionSummary, run_decryption_job
from ccas.ingestor.job import IngestionSummary, run_ingestion_job
from ccas.parser.job import ParseSummary, run_parse_job
from ccas.pipeline.summary import FailedItem, PipelineSummary, StageSummary

logger = logging.getLogger(__name__)


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


async def run_pipeline(session: AsyncSession) -> PipelineSummary:
    """執行五階段 pipeline 並回傳結構化摘要。

    各階段依序執行：ingest -> decrypt -> parse -> classify -> notify。
    每階段部分失敗不阻斷後續階段。前一階段成功輸出作為後一階段輸入
    （透過 DB 狀態欄位串接）。

    Args:
        session: 非同步 DB Session。

    Returns:
        PipelineSummary 包含各階段統計與總耗時。
    """
    start = time.monotonic()

    # Stage 1: Ingest
    logger.info("Pipeline stage 1/5: ingest")
    ingest_result = await run_ingestion_job(session)
    ingest_ss = _ingest_stage_summary(ingest_result)

    # Stage 2: Decrypt
    logger.info("Pipeline stage 2/5: decrypt")
    decrypt_result = await run_decryption_job(session)
    decrypt_ss = _decrypt_stage_summary(decrypt_result)

    # Stage 3: Parse
    logger.info("Pipeline stage 3/5: parse")
    parse_result = await run_parse_job(session)
    parse_ss = _parse_stage_summary(parse_result)

    # Stage 4: Classify
    logger.info("Pipeline stage 4/5: classify")
    classify_result = await run_classify_job(session)
    classify_ss = _classify_stage_summary(classify_result)

    # Stage 5: Notify (send notifications for newly parsed bills)
    logger.info("Pipeline stage 5/5: notify")
    # Collect IDs of newly parsed bills from parse stage
    # Parse stage creates bills via DB; we notify for all successfully parsed items
    notify_result = await run_notify_job(session)
    notify_ss = _notify_stage_summary(notify_result)

    elapsed = time.monotonic() - start
    failures = _collect_failures(ingest_ss, decrypt_ss, parse_ss, notify_ss)

    summary = PipelineSummary(
        stages=(ingest_ss, decrypt_ss, parse_ss, classify_ss, notify_ss),
        total_seconds=round(elapsed, 2),
        failures=failures,
    )

    logger.info(
        "Pipeline completed in %.2fs: ingest=%d decrypt=%d parse=%d classify=%d notify=%d",
        elapsed,
        ingest_result.staged_count,
        decrypt_result.decrypted_count,
        parse_result.parsed_count,
        classify_result.classified_count,
        notify_result.sent_count,
    )

    return summary
