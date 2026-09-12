"""RQ job 封裝與重試邏輯。

將 async run_pipeline() 包裝為 RQ 可執行的同步函式，
並實作指數退避重試（最多 3 次）。
"""

from __future__ import annotations

import asyncio
import logging
from types import TracebackType

from redis import Redis
from rq import Retry
from rq.job import Job

from ccas.pipeline.lifecycle import DbLifecycleStore, LifecycleResult, RunLifecycle
from ccas.pipeline.summary import PipelineSummary
from ccas.storage.models import PipelineRunTerminalReason

logger = logging.getLogger(__name__)

MAX_RETRIES = 3


def _calculate_retry_delays() -> list[int]:
    """計算指數退避延遲秒數：2^0, 2^1, 2^2 = 1, 2, 4（上限 60）。"""
    return [min(2**i, 60) for i in range(MAX_RETRIES)]


def get_retry() -> Retry:
    """建立 RQ Retry 設定：最多 3 次，指數退避。"""
    return Retry(max=MAX_RETRIES, interval=_calculate_retry_delays())


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
    from ccas.bot.job import run_notify_job
    from ccas.pipeline.options import PipelineOptions
    from ccas.pipeline.orchestrator import run_pipeline
    from ccas.pipeline.progress import DbProgressReporter
    from ccas.storage.database import get_engine, get_session_factory

    options = PipelineOptions.from_dict(opts)

    async def _run() -> PipelineSummary:
        session_factory = get_session_factory()
        active_run_id = run_id
        store = DbLifecycleStore(session_factory) if active_run_id is not None else None
        try:
            if store is not None and active_run_id is not None:
                await store.persist_progress(active_run_id)

            reporter = (
                DbProgressReporter(run_id, session_factory)
                if run_id is not None
                else None
            )
            try:
                async with session_factory() as session:
                    # Assembly point: bind the concrete notify stage here so
                    # the orchestrator stays decoupled from the bot layer.
                    result = await run_pipeline(
                        session,
                        options,
                        progress_reporter=reporter,
                        notify_job=run_notify_job,
                    )
            except BaseException as exc:  # noqa: BLE001 — deliberate: must also
                # catch CancelledError/SystemExit so the run never leaks in
                # RUNNING state; the exception is re-raised to preserve RQ retry.
                if store is not None and active_run_id is not None:
                    try:
                        await store.persist_terminal(
                            active_run_id,
                            LifecycleResult.failed(
                                f"{type(exc).__name__}: {exc}",
                                terminal_reason=PipelineRunTerminalReason.WORKER_EXCEPTION,
                            ),
                        )
                    except Exception:
                        logger.error(
                            "Failed to mark pipeline run %s as failed",
                            run_id,
                            exc_info=True,
                        )
                raise

            if store is not None and active_run_id is not None:
                # run_pipeline 雖正常回傳，但任一階段可能失敗（classify 整批
                # rollback，或 ingest/decrypt/parse/notify 的 stage errors）：
                # 不 re-raise，仍回傳 result 作為 RQ job result（保留各階段
                # 摘要供查閱）。
                await store.persist_terminal(
                    active_run_id,
                    RunLifecycle.classify(result),
                )
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


async def mark_manual_review(session, bank_code: str | None = None) -> int:
    """將進行中的 staging 項目標記為 manual_review_needed。

    當 RQ job 重試達上限後呼叫。

    Args:
        session: 非同步 DB Session。
        bank_code: 失敗 run 的目標銀行；有值時僅標記該銀行的項目，
            避免污染其他 run 正在處理的 staging 記錄。``None`` 表示
            全銀行 run，維持原行為。

    Returns:
        受影響的記錄數。
    """
    from sqlalchemy import update

    from ccas.storage.models import StagedAttachment, StagedAttachmentStatus

    stmt = (
        update(StagedAttachment)
        .where(
            StagedAttachment.status.in_(
                [StagedAttachmentStatus.STAGED, StagedAttachmentStatus.DECRYPTED]
            )
        )
        .values(status=StagedAttachmentStatus.MANUAL_REVIEW_NEEDED)
    )
    if bank_code is not None:
        stmt = stmt.where(StagedAttachment.bank_code == bank_code)
    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount  # type: ignore[return-value]


def _extract_bank_code(job: Job) -> str | None:
    """從 RQ job 取出觸發時的 bank_code（opts 以第一個位置參數 enqueue）。"""
    opts = (getattr(job, "kwargs", None) or {}).get("opts")
    if opts is None:
        args = getattr(job, "args", None) or ()
        opts = args[0] if args else None
    if isinstance(opts, dict):
        bank_code = opts.get("bank_code")
        return bank_code if isinstance(bank_code, str) else None
    return None


def on_failure_handler(
    job: Job,
    connection: Redis,  # noqa: ARG001
    typ: type[BaseException],
    value: BaseException,
    traceback: TracebackType | None,  # noqa: ARG001
) -> None:
    """RQ job 失敗 handler：重試達上限後標記 staging 項目。

    兩個標記步驟各自使用獨立 session 與獨立錯誤處理，
    確保 mark_manual_review 失敗不會阻斷 lifecycle 的 terminal 標記。
    """
    if not hasattr(job, "retries_left") or job.retries_left == 0:
        logger.error(
            "Pipeline job %s failed after all retries, marking items for manual review",
            job.id,
        )
        from ccas.storage.database import get_engine, get_session_factory

        async def _mark() -> int:
            session_factory = get_session_factory()
            count = 0
            try:
                try:
                    async with session_factory() as session:
                        count = await mark_manual_review(
                            session, bank_code=_extract_bank_code(job)
                        )
                except Exception:
                    logger.error(
                        "Failed to mark staging items for manual review",
                        exc_info=True,
                    )

                run_id = (getattr(job, "kwargs", None) or {}).get("run_id")
                if run_id:
                    try:
                        await DbLifecycleStore(session_factory).persist_terminal(
                            run_id,
                            LifecycleResult.failed(
                                f"{typ.__name__}: {value}",
                                terminal_reason=PipelineRunTerminalReason.RETRIES_EXHAUSTED,
                            ),
                        )
                    except Exception:
                        logger.error(
                            "Failed to mark pipeline run %s as failed",
                            run_id,
                            exc_info=True,
                        )
            finally:
                await get_engine().dispose()
            return count

        try:
            # asyncio.run() relies on RQ's fork-per-job model (no running
            # loop in this process). Switching to an async worker class
            # requires reworking this handler first, or the RuntimeError
            # would be swallowed below and the run would stay RUNNING.
            count = asyncio.run(_mark())
            logger.info("Marked %d staging items as manual_review_needed", count)
        except Exception:
            logger.error(
                "Failed to mark staging items for manual review", exc_info=True
            )
