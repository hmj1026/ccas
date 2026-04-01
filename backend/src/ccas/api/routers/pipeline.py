"""Pipeline 觸發 API 路由。

提供 POST /api/pipeline/trigger 將 run_pipeline() 加入 RQ 工作隊列。
"""

import logging

from fastapi import APIRouter
from redis import Redis
from rq import Queue

from ccas.api.schemas import ApiResponse, PipelineTriggerData, PipelineTriggerRequest
from ccas.config import get_settings
from ccas.pipeline.worker import get_retry, on_failure_handler, run_pipeline_sync

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])


@router.post("/trigger", response_model=ApiResponse[PipelineTriggerData])
async def trigger_pipeline(
    body: PipelineTriggerRequest | None = None,
) -> ApiResponse[PipelineTriggerData]:
    """將 pipeline 加入 RQ 工作隊列，立即回傳 job ID。

    Args:
        body: 可選的 pipeline 參數（force, bank_code, year, month）。
    """
    settings = get_settings()
    redis_conn = Redis.from_url(settings.redis_url)
    queue = Queue(connection=redis_conn)

    opts = body.model_dump() if body else None

    job = queue.enqueue(
        run_pipeline_sync,
        opts,
        retry=get_retry(),
        on_failure=on_failure_handler,
        job_timeout="30m",
    )

    logger.info("Pipeline job enqueued: %s (opts=%s)", job.id, opts)
    return ApiResponse(
        data=PipelineTriggerData(job_id=job.id),
        message="Pipeline job enqueued",
    )
