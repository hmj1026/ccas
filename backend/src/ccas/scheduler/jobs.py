"""排程工作的同步封裝。

提供 APScheduler 與 RQ 可呼叫的同步函式。
"""

import asyncio
import logging
from uuid import uuid4

from redis import Redis
from rq import Queue

from ccas.config import get_settings

logger = logging.getLogger(__name__)


def trigger_pipeline_via_rq(opts: dict | None = None) -> str:
    """直接將 pipeline enqueue 至 RQ（供 APScheduler 呼叫）。

    Mirrors the API trigger endpoint semantics (see
    ``ccas.api.routers.pipeline.trigger_pipeline``): create the PipelineRun
    row (status=QUEUED) first, enqueue ``run_pipeline_sync``, then persist
    the RQ job id back onto the row.

    Args:
        opts: 可選的 pipeline 參數 dict（force, bank_code, year, month）。

    Returns:
        The RQ job id.
    """
    from ccas.pipeline.worker import get_retry, on_failure_handler, run_pipeline_sync
    from ccas.storage.database import get_engine, get_session_factory
    from ccas.storage.models import PipelineRun, PipelineRunStatus

    params = opts or {}
    run_id = str(uuid4())
    queue = Queue(connection=Redis.from_url(get_settings().redis_url))

    async def _run() -> str:
        session_factory = get_session_factory()
        async with session_factory() as session:
            session.add(
                PipelineRun(
                    id=run_id,
                    job_id=run_id,
                    status=PipelineRunStatus.QUEUED,
                    triggered_by="scheduler",
                    params=params,
                    stage_summary=[],
                )
            )
            await session.commit()

            try:
                # params must stay the first positional arg: the worker's
                # on_failure_handler reads bank_code from job.args[0],
                # identical to the API trigger path.
                job = queue.enqueue(
                    run_pipeline_sync,
                    params,
                    run_id=run_id,
                    retry=get_retry(),
                    on_failure=on_failure_handler,
                    job_timeout="30m",
                )
            except Exception:
                # Enqueue failed: the job never entered the queue, so the RQ
                # on_failure callback can never fire. Mark the orphan QUEUED row
                # FAILED so it does not linger forever (mirrors the API path).
                run = await session.get(PipelineRun, run_id)
                if run is not None:
                    run.status = PipelineRunStatus.FAILED
                    run.error_message = "Pipeline enqueue failed (scheduler)"
                    await session.commit()
                raise

            run = await session.get(PipelineRun, run_id)
            if run is not None:
                run.job_id = job.id
                await session.commit()
        await get_engine().dispose()
        return job.id

    # asyncio.run() assumes no running event loop (APScheduler executes this
    # in a plain sync thread); revisit before moving to an async scheduler.
    try:
        job_id = asyncio.run(_run())
    except Exception:
        # APScheduler swallows unhandled exceptions into framework logs at a
        # level operators may not see; log explicitly here. The PipelineRun row
        # (if created) was already marked FAILED inside _run().
        logger.exception(
            "Scheduler pipeline trigger failed (run_id=%s, opts=%s)",
            run_id,
            params,
        )
        raise
    logger.info(
        "Pipeline job enqueued by scheduler: %s (run_id=%s, opts=%s)",
        job_id,
        run_id,
        params,
    )
    return job_id


def run_payment_reminders_sync() -> dict[str, int]:
    """同步執行付款提醒（供 APScheduler 呼叫）。"""
    from ccas.scheduler.reminders import send_payment_reminders
    from ccas.storage.database import get_engine, get_session_factory

    async def _run() -> dict[str, int]:
        session_factory = get_session_factory()
        async with session_factory() as session:
            result = await send_payment_reminders(session)
        await get_engine().dispose()
        return result

    try:
        result = asyncio.run(_run())
    except Exception:
        # APScheduler swallows unhandled exceptions into framework logs; surface
        # them explicitly so operators can act on a failed reminder run.
        logger.exception("Scheduler payment reminders failed")
        raise
    logger.info(
        "Payment reminders: sent=%d, skipped=%d", result["sent"], result["skipped"]
    )
    return result


def run_budget_evaluator_sync() -> dict[str, int]:
    """同步執行預算評估（供 APScheduler 呼叫）。"""
    from ccas.scheduler.budget_evaluator import evaluate_budgets
    from ccas.storage.database import get_engine, get_session_factory

    async def _run() -> dict[str, int]:
        session_factory = get_session_factory()
        async with session_factory() as session:
            result = await evaluate_budgets(session)
        await get_engine().dispose()
        return result

    try:
        result = asyncio.run(_run())
    except Exception:
        # APScheduler swallows unhandled exceptions into framework logs; surface
        # them explicitly so operators can act on a failed evaluator run.
        logger.exception("Scheduler budget evaluator failed")
        raise
    logger.info(
        "Budget evaluator: alerts_triggered=%d, skipped=%d",
        result["alerts_triggered"],
        result["skipped"],
    )
    return result
