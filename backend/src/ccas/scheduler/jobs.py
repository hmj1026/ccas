"""排程工作的同步封裝。

提供 APScheduler 與 RQ 可呼叫的同步函式。
"""

import asyncio
import logging

from redis import Redis
from rq import Queue

from ccas.config import get_settings
from ccas.pipeline.submission import (
    PipelineEnqueueError,
    RqPipelineQueue,
    submit_pipeline,
)

logger = logging.getLogger(__name__)


def trigger_pipeline_via_rq(opts: dict | None = None) -> str:
    """Submit through the shared lifecycle from APScheduler's sync thread."""
    from ccas.storage.database import get_engine, get_session_factory

    params = opts or {}
    queue = RqPipelineQueue(Queue(connection=Redis.from_url(get_settings().redis_url)))

    async def _run() -> str:
        try:
            async with get_session_factory()() as session:
                result = await submit_pipeline(
                    session, queue, params, triggered_by="scheduler"
                )
                return result.job_id
        except PipelineEnqueueError as exc:
            # Preserve the scheduler's original queue exception contract.
            raise exc.cause from None
        finally:
            # asyncio.run closes its loop; release connections on both outcomes.
            await get_engine().dispose()

    try:
        job_id = asyncio.run(_run())
    except Exception:
        logger.exception("Scheduler pipeline trigger failed (opts=%s)", params)
        raise
    logger.info("Pipeline job enqueued by scheduler: %s (opts=%s)", job_id, params)
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
