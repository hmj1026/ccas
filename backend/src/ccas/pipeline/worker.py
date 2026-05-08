"""RQ job 封裝與重試邏輯。

將 async run_pipeline() 包裝為 RQ 可執行的同步函式，
並實作指數退避重試（最多 3 次）。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from types import TracebackType

from redis import Redis
from rq import Retry
from rq.job import Job
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.pipeline.summary import PipelineSummary
from ccas.storage.models import PipelineRun, PipelineRunStatus

logger = logging.getLogger(__name__)

MAX_RETRIES = 3


def _calculate_retry_delays() -> list[int]:
    """計算指數退避延遲秒數：2^0, 2^1, 2^2 = 1, 2, 4（上限 60）。"""
    return [min(2**i, 60) for i in range(MAX_RETRIES)]


def get_retry() -> Retry:
    """建立 RQ Retry 設定：最多 3 次，指數退避。"""
    return Retry(max=MAX_RETRIES, interval=_calculate_retry_delays())


async def _set_pipeline_run_status(
    session: AsyncSession,
    run_id: str,
    status: PipelineRunStatus,
    *,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    error_message: str | None = None,
) -> None:
    """寫入 PipelineRun 狀態與對應時間戳。

    僅設置呼叫端顯式傳入的欄位（``None`` 不寫入），避免在 running → failed
    轉換時誤覆寫 ``started_at``。
    """
    values: dict[str, object] = {"status": status}
    if started_at is not None:
        values["started_at"] = started_at
    if completed_at is not None:
        values["completed_at"] = completed_at
    if error_message is not None:
        values["error_message"] = error_message

    await session.execute(
        update(PipelineRun).where(PipelineRun.id == run_id).values(**values)
    )
    await session.commit()


async def mark_pipeline_run_running(session: AsyncSession, run_id: str) -> None:
    """將 PipelineRun 標記為 running 並記錄 started_at。"""
    await _set_pipeline_run_status(
        session,
        run_id,
        PipelineRunStatus.RUNNING,
        started_at=datetime.now(UTC),
    )


async def mark_pipeline_run_succeeded(session: AsyncSession, run_id: str) -> None:
    """將 PipelineRun 標記為 succeeded 並記錄 completed_at。"""
    await _set_pipeline_run_status(
        session,
        run_id,
        PipelineRunStatus.SUCCEEDED,
        completed_at=datetime.now(UTC),
    )


async def mark_pipeline_run_failed(
    session: AsyncSession, run_id: str, error_message: str
) -> None:
    """將 PipelineRun 標記為 failed 並記錄錯誤訊息。"""
    await _set_pipeline_run_status(
        session,
        run_id,
        PipelineRunStatus.FAILED,
        completed_at=datetime.now(UTC),
        error_message=error_message,
    )


def run_pipeline_sync(opts: dict | None = None, run_id: str | None = None) -> dict:
    """RQ worker 執行的同步入口。

    建立 async event loop 執行 run_pipeline()，
    回傳可序列化的摘要 dict 作為 RQ job result。

    Args:
        opts: 可選的 pipeline 參數 dict（由 API 端序列化傳入）。
        run_id: 可選的 PipelineRun id（由 API trigger 建 row 後傳入）。

    若執行失敗且重試次數已達上限，將所有 staging 項目
    標記為 manual_review_needed。
    """
    from ccas.pipeline.options import PipelineOptions
    from ccas.pipeline.orchestrator import run_pipeline
    from ccas.pipeline.progress import DbProgressReporter
    from ccas.storage.database import get_engine, get_session_factory

    options = PipelineOptions.from_dict(opts)

    async def _run() -> PipelineSummary:
        session_factory = get_session_factory()
        try:
            if run_id is not None:
                async with session_factory() as session:
                    await mark_pipeline_run_running(session, run_id)

            reporter = (
                DbProgressReporter(run_id, session_factory)
                if run_id is not None
                else None
            )
            async with session_factory() as session:
                result = await run_pipeline(
                    session, options, progress_reporter=reporter
                )

            if run_id is not None:
                async with session_factory() as session:
                    await mark_pipeline_run_succeeded(session, run_id)
            return result
        finally:
            await get_engine().dispose()

    summary = asyncio.run(_run())
    return {
        "total_seconds": summary.total_seconds,
        "stages": [
            {"stage": s.stage, "counts": s.counts, "errors": s.errors}
            for s in summary.stages
        ],
        "failures": [
            {"item_id": f.item_id, "error": f.error} for f in summary.failures
        ],
    }


async def mark_manual_review(session) -> int:
    """將所有進行中的 staging 項目標記為 manual_review_needed。

    當 RQ job 重試達上限後呼叫。

    Args:
        session: 非同步 DB Session。

    Returns:
        受影響的記錄數。
    """
    from sqlalchemy import update

    from ccas.storage.models import StagedAttachment

    stmt = (
        update(StagedAttachment)
        .where(StagedAttachment.status.in_(["staged", "decrypted"]))
        .values(status="manual_review_needed")
    )
    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount  # type: ignore[return-value]


def on_failure_handler(
    job: Job,
    connection: Redis,  # noqa: ARG001
    typ: type[BaseException],  # noqa: ARG001
    value: BaseException,  # noqa: ARG001
    traceback: TracebackType | None,  # noqa: ARG001
) -> None:
    """RQ job 失敗 handler：重試達上限後標記 staging 項目。"""
    if not hasattr(job, "retries_left") or job.retries_left == 0:
        logger.error(
            "Pipeline job %s failed after all retries, marking items for manual review",
            job.id,
        )
        from ccas.storage.database import get_engine, get_session_factory

        async def _mark() -> int:
            session_factory = get_session_factory()
            async with session_factory() as session:
                count = await mark_manual_review(session)
                run_id = getattr(job, "kwargs", {}).get("run_id")
                if run_id:
                    error_message = f"{typ.__name__}: {value}"
                    await mark_pipeline_run_failed(session, run_id, error_message)
            await get_engine().dispose()
            return count

        try:
            count = asyncio.run(_mark())
            logger.info("Marked %d staging items as manual_review_needed", count)
        except Exception:
            logger.error(
                "Failed to mark staging items for manual review", exc_info=True
            )
