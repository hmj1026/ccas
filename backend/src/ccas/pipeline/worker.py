"""RQ job 封裝與重試邏輯。

將 async run_pipeline() 包裝為 RQ 可執行的同步函式，
並實作指數退避重試（最多 3 次）。
"""

import asyncio
import logging
import math

from rq import Retry

from ccas.config import get_settings
from ccas.pipeline.summary import PipelineSummary

logger = logging.getLogger(__name__)

MAX_RETRIES = 3


def _calculate_retry_delays() -> list[int]:
    """計算指數退避延遲秒數：2^0, 2^1, 2^2 = 1, 2, 4（上限 60）。"""
    return [min(2**i, 60) for i in range(MAX_RETRIES)]


def get_retry() -> Retry:
    """建立 RQ Retry 設定：最多 3 次，指數退避。"""
    return Retry(max=MAX_RETRIES, interval=_calculate_retry_delays())


def run_pipeline_sync() -> dict:
    """RQ worker 執行的同步入口。

    建立 async event loop 執行 run_pipeline()，
    回傳可序列化的摘要 dict 作為 RQ job result。

    若執行失敗且重試次數已達上限，將所有 staging 項目
    標記為 manual_review_needed。
    """
    from ccas.pipeline.orchestrator import run_pipeline
    from ccas.storage.database import get_engine, get_session_factory

    async def _run() -> PipelineSummary:
        engine = get_engine()
        session_factory = get_session_factory(engine)
        async with session_factory() as session:
            result = await run_pipeline(session)
        await engine.dispose()
        return result

    summary = asyncio.run(_run())
    return {
        "total_seconds": summary.total_seconds,
        "stages": [
            {"stage": s.stage, "counts": s.counts, "errors": s.errors}
            for s in summary.stages
        ],
        "failures": [
            {"item_id": f.item_id, "error": f.error}
            for f in summary.failures
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
        .where(
            StagedAttachment.status.in_(["staged", "decrypted"])
        )
        .values(status="manual_review_needed")
    )
    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount  # type: ignore[return-value]


def on_failure_handler(job, connection, typ, value, traceback):
    """RQ job 失敗 handler：重試達上限後標記 staging 項目。"""
    if not hasattr(job, "retries_left") or job.retries_left == 0:
        logger.error(
            "Pipeline job %s failed after all retries, marking items for manual review",
            job.id,
        )
        from ccas.storage.database import get_engine, get_session_factory

        async def _mark():
            engine = get_engine()
            session_factory = get_session_factory(engine)
            async with session_factory() as session:
                count = await mark_manual_review(session)
            await engine.dispose()
            return count

        count = asyncio.run(_mark())
        logger.info("Marked %d staging items as manual_review_needed", count)
