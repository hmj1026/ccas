"""Pipeline 觸發 API 路由。

提供 POST /api/pipeline/trigger 將 run_pipeline() 加入 RQ 工作隊列。
"""

import logging
from typing import Any, NoReturn, cast

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import JSONResponse
from redis import Redis
from rq import Queue
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.api.deps import PaginationParams
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
from ccas.pipeline.submission import (
    PipelineEnqueueError,
    RqPipelineQueue,
    submit_pipeline,
)
from ccas.services.pipeline import (
    get_pipeline_run as service_get_pipeline_run,
)
from ccas.services.pipeline import (
    list_pipeline_runs as service_list_pipeline_runs,
)
from ccas.services.pipeline import (
    pipeline_status,
)
from ccas.services.schemas import AgentQueryError, PipelineStatus
from ccas.storage.database import get_db_session
from ccas.storage.models import (
    PipelineRun,
    PipelineRunStatus,
)

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


def _handle_agent_query_error(exc: AgentQueryError) -> NoReturn:
    if exc.code == "resource_not_found":
        raise HTTPException(status_code=404, detail=exc.message)
    if exc.code == "invalid_argument":
        raise HTTPException(status_code=422, detail=exc.message)
    raise HTTPException(status_code=500, detail=exc.message)


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
    try:
        result = await submit_pipeline(
            session, RqPipelineQueue(queue), opts, triggered_by="api"
        )
    except PipelineEnqueueError as exc:
        return JSONResponse(
            status_code=503,
            content={"success": False, "message": str(exc), "data": None},
        )

    logger.info("Pipeline job enqueued: %s (opts=%s)", result.job_id, opts)
    return ApiResponse(
        data=PipelineTriggerData(job_id=result.job_id, run_id=result.run_id),
        message="Pipeline job enqueued",
    )


def _stage_entries(raw: list[dict[str, Any]] | None) -> list[PipelineStageEntry]:
    return [PipelineStageEntry.model_validate(item) for item in (raw or [])]


def _raw_summary_to_item(raw: dict[str, Any]) -> PipelineRunSummary:
    status = cast(PipelineRunStatusLiteral, raw["status"])
    return PipelineRunSummary(
        id=raw["id"],
        job_id=raw["job_id"],
        status=status,
        triggered_by=raw["triggered_by"],
        params=raw["params"],
        current_stage=raw["current_stage"],
        current_stage_processed=raw["current_stage_processed"],
        current_stage_total=raw["current_stage_total"],
        stage_summary=_stage_entries(raw.get("stage_summary")),
        error_message=raw["error_message"],
        started_at=raw["started_at"],
        completed_at=raw["completed_at"],
        created_at=raw["created_at"],
        updated_at=raw["updated_at"],
    )


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


@router.get("/status", response_model=ApiResponse[PipelineStatus])
async def get_pipeline_status(
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[PipelineStatus]:
    """取得最新一次 pipeline 執行狀態。"""
    try:
        projection = await pipeline_status(session)
    except AgentQueryError as exc:
        _handle_agent_query_error(exc)

    return ApiResponse(data=projection.payload.data)


@router.get("/runs", response_model=PaginatedResponse[PipelineRunSummary])
async def list_pipeline_runs(
    response: Response,
    status: PipelineRunStatus | None = None,
    pagination: PaginationParams = Depends(),
    session: AsyncSession = Depends(get_db_session),
) -> PaginatedResponse[PipelineRunSummary]:
    """列出最近的 pipeline 執行紀錄（page/page_size 分頁）。

    分頁參數與 /api/bills、/api/transactions 等列表一致，統一走
    ``PaginationParams``（``page``/``page_size``，預設 1/20，page_size 上限 100），
    回應採統一 ``PaginatedResponse`` 信封。為向下相容仍保留 ``X-Total-Count``
    header（未過濾的總筆數）。page < 1 或 page_size 超出 1-100 回 422。
    """
    try:
        projection = await service_list_pipeline_runs(
            session,
            status=status,
            page=pagination.page,
            page_size=pagination.page_size,
        )
    except AgentQueryError as exc:
        _handle_agent_query_error(exc)

    total = projection.rest_metadata["total"]
    raw_summaries = projection.rest_metadata["raw_summaries"]
    response.headers["X-Total-Count"] = str(total)
    return PaginatedResponse(
        data=[_raw_summary_to_item(r) for r in raw_summaries],
        pagination=PaginationMeta(
            page=pagination.page,
            page_size=pagination.page_size,
            total=total,
            total_pages=max(
                1, (total + pagination.page_size - 1) // pagination.page_size
            ),
        ),
    )


@router.get("/runs/{run_id}", response_model=ApiResponse[PipelineRunDetail])
async def get_pipeline_run(
    run_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[PipelineRunDetail]:
    """取得單筆 pipeline 執行紀錄詳情。"""
    try:
        projection = await service_get_pipeline_run(session, run_id)
    except AgentQueryError as exc:
        _handle_agent_query_error(exc)

    raw = projection.rest_metadata["raw_summary"]
    summary = _raw_summary_to_item(raw)
    return ApiResponse(data=PipelineRunDetail.model_validate(summary.model_dump()))
