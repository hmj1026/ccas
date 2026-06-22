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


def _classify_batch_failed(summary: PipelineSummary) -> bool:
    """偵測 classify 階段是否整批 commit 失敗。

    classify 是 all-or-nothing：``_flush_commit_or_rollback`` 失敗時會 rollback
    整批並拋 ``ClassifyError``，但 ``orchestrator._run_stage`` 將其捕捉成
    ``StageSummary(counts={"failed": 1})`` 後 ``run_pipeline`` 仍正常回傳。
    若不偵測，worker 會誤呼叫 ``mark_pipeline_run_succeeded``，導致分類結果已
    全數 rollback 卻標記成功。成功路徑的 classify 摘要為
    ``counts={"classified": N}``（無 ``failed`` 鍵），因此以 ``failed > 0``
    作為整批失敗的判定訊號。
    """
    for stage in summary.stages:
        if stage.stage == "classify" and stage.counts.get("failed", 0) > 0:
            return True
    return False


def _run_failure_reason(summary: PipelineSummary) -> str | None:
    """回傳應將 run 標記為 FAILED 的原因字串，否則 None（成功）。

    兩類失敗訊號：
    - classify 整批 rollback：以 ``counts['failed']`` 表示（無 errors），
      由 ``_classify_batch_failed`` 偵測，優先回傳明確訊息。
    - 其他階段（ingest/decrypt/parse/notify）的錯誤：以 stage.errors 記錄並
      聚合進 ``summary.failures``。此前 worker 只看 classify counts，使得
      Gmail 分頁中途失敗等情形 failed_count 維持 0 卻仍被標 SUCCEEDED，
      N 封郵件靜默遺漏。改為只要有任一階段失敗即標 FAILED（對齊 CLI 以
      ``summary.failures`` 非空 exit 1 的語意）。
    """
    if _classify_batch_failed(summary):
        return "classify 階段整批 commit 失敗，分類結果已 rollback"
    # 直接掃資料階段 errors（不依賴 orchestrator 是否已聚合進 summary.failures），
    # 涵蓋 ingest 分頁中途失敗等「counts.failed=0 但有錯誤字串」的靜默資料遺漏。
    # 排除 ``notify``：通知為盡力而為通道（Telegram 單筆逾時等），帳單資料此時
    # 已完整持久化，且 notify 自身以 PaymentReminder 唯一鍵冪等重試——單筆通知
    # 失敗不應讓整個 run 在儀表板顯示 FAILED（誤導操作員以為資料管線壞了）。
    stage_errors = [
        (stage.stage, err)
        for stage in summary.stages
        if stage.stage != "notify"
        for err in stage.errors
    ]
    if stage_errors:
        first_stage, first_err = stage_errors[0]
        return (
            f"pipeline 有 {len(stage_errors)} 項階段失敗"
            f"（首例 {first_stage}：{first_err}）"
        )
    return None


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
        try:
            if run_id is not None:
                async with session_factory() as session:
                    await mark_pipeline_run_running(session, run_id)

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
                if run_id is not None:
                    try:
                        async with session_factory() as session:
                            await mark_pipeline_run_failed(
                                session,
                                run_id,
                                f"{type(exc).__name__}: {exc}",
                            )
                    except Exception:
                        logger.error(
                            "Failed to mark pipeline run %s as failed",
                            run_id,
                            exc_info=True,
                        )
                raise

            if run_id is not None:
                failure_reason = _run_failure_reason(result)
                if failure_reason is not None:
                    # 任一階段失敗（classify 整批 rollback，或 ingest/decrypt/
                    # parse/notify 的 stage errors）：run_pipeline 雖正常回傳，但
                    # 有資料遺漏/未處理，必須標 FAILED 而非 SUCCEEDED。不 re-raise，
                    # 仍回傳 result 作為 RQ job result（保留各階段摘要供查閱）。
                    async with session_factory() as session:
                        await mark_pipeline_run_failed(session, run_id, failure_reason)
                else:
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
    確保 mark_manual_review 失敗不會阻斷 mark_pipeline_run_failed。
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
                        async with session_factory() as session:
                            await mark_pipeline_run_failed(
                                session, run_id, f"{typ.__name__}: {value}"
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
