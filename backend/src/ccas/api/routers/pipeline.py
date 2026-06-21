"""Pipeline 觸發 API 路由。

提供 POST /api/pipeline/trigger 將 run_pipeline() 加入 RQ 工作隊列。
"""

import logging
from typing import cast
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import JSONResponse
from redis import Redis
from rq import Queue
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.api.schemas import (
    ApiResponse,
    PaginatedResponse,
    PaginationMeta,
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
) -> ApiResponse[PipelineTriggerData] | JSONResponse:
    """將 pipeline 加入 RQ 工作隊列，立即回傳 job ID。

    Args:
        body: 可選的 pipeline 參數（force, bank_code, year, month）。

    若 Redis 不可達導致 enqueue 失敗，會把先前建立的 QUEUED row 標記為
    FAILED（避免留下永不執行的 orphan row），並回傳 503 統一信封。
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

    try:
        job = queue.enqueue(
            run_pipeline_sync,
            opts,
            run_id=run_id,
            retry=get_retry(),
            on_failure=on_failure_handler,
            job_timeout="30m",
        )
    except Exception as exc:
        # Enqueue failed (RedisError / connection refused / any unexpected
        # error): the job never entered the queue, so the RQ on_failure
        # callback can never fire. Mark the orphan QUEUED row FAILED here so it
        # does not linger forever as "queued". Broad catch is intentional and
        # logged below (logger.exception) — never a silent failure.
        logger.exception("Pipeline enqueue failed (run_id=%s)", run_id)
        error_message = f"Pipeline enqueue failed: {exc}"
        run = await session.get(PipelineRun, run_id)
        if run is not None:
            run.status = PipelineRunStatus.FAILED
            run.error_message = error_message
            await session.commit()
        # Return the project's ApiResponse error envelope (success=false)
        # directly. A raised HTTPException would now also be wrapped into this
        # envelope by the app-level handler, but building the JSONResponse here
        # keeps the orphan-row FAILED bookkeeping above in the same code path.
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "message": error_message,
                "data": None,
            },
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


@router.get("/runs", response_model=PaginatedResponse[PipelineRunSummary])
async def list_pipeline_runs(
    response: Response,
    status: PipelineRunStatus | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db_session),
) -> PaginatedResponse[PipelineRunSummary]:
    """列出最近的 pipeline 執行紀錄（支援 offset 分頁）。

    回應採統一 ``PaginatedResponse`` 信封（與 /api/bills 等列表一致），``pagination``
    由 limit/offset 換算。為向下相容仍保留 ``X-Total-Count`` header（未過濾的總筆數）。
    limit 超出 1-100 或 offset < 0 回 422。

    註：``pagination.page`` 以 ``floor(offset/limit)+1`` 計，僅在 offset 為 limit
    倍數時精確；本端點以 limit/offset 為分頁真值，``page`` 為便利欄位。
    """
    # Total over the SAME status filter but ignoring limit/offset, so the
    # frontend knows when it has paged through every matching run.
    count_stmt = select(func.count()).select_from(PipelineRun)
    page_stmt = select(PipelineRun)
    if status is not None:
        count_stmt = count_stmt.where(PipelineRun.status == status)
        page_stmt = page_stmt.where(PipelineRun.status == status)
    page_stmt = (
        page_stmt.order_by(PipelineRun.created_at.desc()).offset(offset).limit(limit)
    )

    total = (await session.execute(count_stmt)).scalar_one()
    rows = (await session.execute(page_stmt)).scalars().all()
    response.headers["X-Total-Count"] = str(total)
    return PaginatedResponse(
        data=[_run_summary(row) for row in rows],
        pagination=PaginationMeta(
            # limit≥1（Query 約束）故無除零風險；offset 為 limit 倍數時頁碼精確。
            page=(offset // limit) + 1,
            page_size=limit,
            total=total,
            total_pages=max(1, (total + limit - 1) // limit),
        ),
    )


@router.get("/runs/{run_id}", response_model=ApiResponse[PipelineRunDetail])
async def get_pipeline_run(
    run_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[PipelineRunDetail]:
    """取得單筆 pipeline 執行紀錄詳情。"""
    row = await session.get(PipelineRun, run_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"找不到執行紀錄 #{run_id}")

    return ApiResponse(
        data=PipelineRunDetail.model_validate(_run_summary(row).model_dump())
    )
