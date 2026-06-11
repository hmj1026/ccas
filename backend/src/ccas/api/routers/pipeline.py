"""Pipeline 觸發 API 路由。

提供 POST /api/pipeline/trigger 將 run_pipeline() 加入 RQ 工作隊列。
"""

import logging
from typing import cast
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from redis import Redis
from rq import Queue
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.api.schemas import (
    ApiResponse,
    PipelineRunDetail,
    PipelineRunStatusLiteral,
    PipelineRunSummary,
    PipelineStageEntry,
    PipelineTriggerData,
    PipelineTriggerRequest,
)
from ccas.config import get_settings
from ccas.pipeline.worker import get_retry, on_failure_handler, run_pipeline_sync
from ccas.storage.database import get_db_session
from ccas.storage.models import PipelineRun, PipelineRunStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])

# Process-wide Redis connection (lazy singleton)；避免每次 trigger 都新建
# TCP 連線。RQ enqueue 為 sync 操作，沿用 sync client。
_redis_pool: Redis | None = None


def get_redis_client() -> Redis:
    """回傳 process 級 Redis 連線單例（首次呼叫時建立）。"""
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = Redis.from_url(get_settings().redis_url)
    return _redis_pool


@router.post("/trigger", response_model=ApiResponse[PipelineTriggerData])
async def trigger_pipeline(
    body: PipelineTriggerRequest | None = None,
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[PipelineTriggerData]:
    """將 pipeline 加入 RQ 工作隊列，立即回傳 job ID。

    Args:
        body: 可選的 pipeline 參數（force, bank_code, year, month）。
    """
    queue = Queue(connection=get_redis_client())

    request = body or PipelineTriggerRequest()
    opts = request.model_dump()
    run_id = str(uuid4())
    session.add(
        PipelineRun(
            id=run_id,
            job_id=run_id,
            status=PipelineRunStatus.QUEUED,
            triggered_by="api",
            params=opts,
            stage_summary=[],
        )
    )
    await session.commit()

    job = queue.enqueue(
        run_pipeline_sync,
        opts,
        run_id=run_id,
        retry=get_retry(),
        on_failure=on_failure_handler,
        job_timeout="30m",
    )

    run = await session.get(PipelineRun, run_id)
    if run is not None:
        run.job_id = job.id
        await session.commit()

    logger.info("Pipeline job enqueued: %s (opts=%s)", job.id, opts)
    return ApiResponse(
        data=PipelineTriggerData(job_id=job.id, run_id=run_id),
        message="Pipeline job enqueued",
    )


def _stage_entries(raw: list[dict] | None) -> list[PipelineStageEntry]:
    return [PipelineStageEntry.model_validate(item) for item in (raw or [])]


def _run_summary(row: PipelineRun) -> PipelineRunSummary:
    status = cast(PipelineRunStatusLiteral, row.status)
    return PipelineRunSummary(
        id=row.id,
        job_id=row.job_id,
        status=status,
        triggered_by=row.triggered_by,
        params=row.params,
        current_stage=row.current_stage,
        current_stage_processed=row.current_stage_processed,
        current_stage_total=row.current_stage_total,
        stage_summary=_stage_entries(row.stage_summary),
        error_message=row.error_message,
        started_at=row.started_at,
        completed_at=row.completed_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("/runs", response_model=ApiResponse[list[PipelineRunSummary]])
async def list_pipeline_runs(
    status: PipelineRunStatus | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[list[PipelineRunSummary]]:
    """列出最近的 pipeline 執行紀錄。limit 超出 1-100 回 422。"""
    stmt = select(PipelineRun)
    if status is not None:
        stmt = stmt.where(PipelineRun.status == status)
    stmt = stmt.order_by(PipelineRun.created_at.desc()).limit(limit)

    rows = (await session.execute(stmt)).scalars().all()
    return ApiResponse(data=[_run_summary(row) for row in rows])


@router.get("/runs/{run_id}", response_model=ApiResponse[PipelineRunDetail])
async def get_pipeline_run(
    run_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[PipelineRunDetail]:
    """取得單筆 pipeline 執行紀錄詳情。"""
    row = await session.get(PipelineRun, run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Pipeline run not found")

    return ApiResponse(
        data=PipelineRunDetail.model_validate(_run_summary(row).model_dump())
    )
