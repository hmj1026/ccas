"""Pipeline runs API integration tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.api.routers import pipeline as pipeline_module
from ccas.storage.models import PipelineRun, PipelineRunStatus
from tests.integration.conftest import auth_headers


@pytest.fixture(autouse=True)
def _reset_redis_singleton():
    """Reset the module-level Redis singleton so each test re-resolves it."""
    pipeline_module._redis_pool = None
    yield
    pipeline_module._redis_pool = None


def _make_run(
    run_id: str,
    *,
    status: PipelineRunStatus = PipelineRunStatus.QUEUED,
    created_at: datetime | None = None,
) -> PipelineRun:
    return PipelineRun(
        id=run_id,
        job_id=f"job-{run_id}",
        status=status,
        triggered_by="api",
        params={"force": False, "bank_code": "CTBC"},
        current_stage="parse",
        current_stage_processed=2,
        current_stage_total=5,
        stage_summary=[
            {
                "stage": "ingest",
                "ok": 2,
                "fail": 0,
                "elapsed_ms": 10,
                "counts": {"staged": 2, "failed": 0},
                "errors": [],
            }
        ],
        error_message="boom" if status == PipelineRunStatus.FAILED else None,
        started_at=created_at,
        completed_at=created_at,
        created_at=created_at or datetime.now(UTC),
        updated_at=created_at or datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_trigger_creates_queued_run_and_returns_run_id(
    client: AsyncClient, db_session: AsyncSession
):
    mock_job = MagicMock()
    mock_job.id = "rq-job-1"
    mock_queue = MagicMock()
    mock_queue.enqueue.return_value = mock_job

    with (
        patch("ccas.api.routers.pipeline.Redis"),
        patch("ccas.api.routers.pipeline.Queue", return_value=mock_queue),
    ):
        response = await client.post(
            "/api/pipeline/trigger",
            headers=auth_headers(),
            json={"force": True, "bank_code": "CTBC", "year": 2026, "month": 3},
        )

    assert response.status_code == 200
    body = response.json()
    run_id = body["data"]["run_id"]
    assert body["data"]["job_id"] == "rq-job-1"
    assert run_id

    run = await db_session.get(PipelineRun, run_id)
    assert run is not None
    assert run.status == PipelineRunStatus.QUEUED
    assert run.job_id == "rq-job-1"
    assert run.triggered_by == "api"
    assert run.params == {
        "force": True,
        "bank_code": "CTBC",
        "year": 2026,
        "month": 3,
        "from_stage": None,
        "to_stage": None,
    }

    enqueue_call = mock_queue.enqueue.call_args
    assert enqueue_call.kwargs["run_id"] == run_id


@pytest.mark.asyncio
async def test_list_pipeline_runs_filters_status_and_orders_desc(
    client: AsyncClient, db_session: AsyncSession
):
    now = datetime.now(UTC)
    db_session.add_all(
        [
            _make_run(
                "old-failed",
                status=PipelineRunStatus.FAILED,
                created_at=now - timedelta(days=1),
            ),
            _make_run(
                "new-failed",
                status=PipelineRunStatus.FAILED,
                created_at=now,
            ),
            _make_run(
                "running",
                status=PipelineRunStatus.RUNNING,
                created_at=now + timedelta(seconds=1),
            ),
        ]
    )
    await db_session.commit()

    response = await client.get(
        "/api/pipeline/runs?status=failed&limit=10", headers=auth_headers()
    )

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body["data"]] == ["new-failed", "old-failed"]
    assert all(item["status"] == "failed" for item in body["data"])


@pytest.mark.asyncio
async def test_list_pipeline_runs_offset_pagination_and_total_header(
    client: AsyncClient, db_session: AsyncSession
):
    """offset 分頁取下一頁；X-Total-Count 回未分頁的總筆數。"""
    now = datetime.now(UTC)
    # 5 runs, created_at strictly increasing so DESC order is deterministic.
    db_session.add_all(
        [_make_run(f"run-{i}", created_at=now + timedelta(seconds=i)) for i in range(5)]
    )
    await db_session.commit()

    # Page 1: limit=2 → newest two (run-4, run-3); header reports full count 5.
    page1 = await client.get(
        "/api/pipeline/runs?limit=2&offset=0", headers=auth_headers()
    )
    assert page1.status_code == 200
    assert page1.headers["X-Total-Count"] == "5"
    page1_ids = [item["id"] for item in page1.json()["data"]]
    assert page1_ids == ["run-4", "run-3"]

    # Page 2: same limit, offset=2 → next two (run-2, run-1); count unchanged.
    page2 = await client.get(
        "/api/pipeline/runs?limit=2&offset=2", headers=auth_headers()
    )
    assert page2.status_code == 200
    assert page2.headers["X-Total-Count"] == "5"
    page2_ids = [item["id"] for item in page2.json()["data"]]
    assert page2_ids == ["run-2", "run-1"]
    # No overlap between pages.
    assert set(page1_ids).isdisjoint(page2_ids)


@pytest.mark.asyncio
async def test_list_pipeline_runs_returns_pagination_envelope(
    client: AsyncClient, db_session: AsyncSession
):
    """R-api-pagination：/runs 改用統一 PaginatedResponse 信封；

    ``pagination`` 由 limit/offset 換算，``X-Total-Count`` header 仍保留（向下相容）。
    """
    now = datetime.now(UTC)
    db_session.add_all(
        [_make_run(f"r-{i}", created_at=now + timedelta(seconds=i)) for i in range(5)]
    )
    await db_session.commit()

    resp = await client.get(
        "/api/pipeline/runs?limit=2&offset=2", headers=auth_headers()
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["pagination"] == {
        "page": 2,
        "page_size": 2,
        "total": 5,
        "total_pages": 3,
    }
    # 既有消費者（讀 data / header）不受影響。
    assert [item["id"] for item in body["data"]] == ["r-2", "r-1"]
    assert resp.headers["X-Total-Count"] == "5"


@pytest.mark.asyncio
async def test_list_pipeline_runs_rejects_negative_offset(client: AsyncClient):
    """offset < 0 回 422（統一信封格式）。"""
    response = await client.get("/api/pipeline/runs?offset=-1", headers=auth_headers())
    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert "offset" in body["message"]


@pytest.mark.asyncio
async def test_pipeline_run_detail_shape(client: AsyncClient, db_session: AsyncSession):
    db_session.add(_make_run("detail-1", status=PipelineRunStatus.FAILED))
    await db_session.commit()

    response = await client.get("/api/pipeline/runs/detail-1", headers=auth_headers())

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["id"] == "detail-1"
    assert body["status"] == "failed"
    assert body["params"]["bank_code"] == "CTBC"
    assert body["current_stage"] == "parse"
    assert body["current_stage_processed"] == 2
    assert body["current_stage_total"] == 5
    assert body["stage_summary"] == [
        {
            "stage": "ingest",
            "ok": 2,
            "fail": 0,
            "elapsed_ms": 10,
            "counts": {"staged": 2, "failed": 0},
            "errors": [],
        }
    ]
    assert body["error_message"] == "boom"
    assert body["triggered_by"] == "api"


@pytest.mark.asyncio
async def test_pipeline_run_detail_not_found(client: AsyncClient):
    response = await client.get("/api/pipeline/runs/missing", headers=auth_headers())

    assert response.status_code == 404
    # 404 message is Traditional Chinese and echoes the requested run_id.
    assert response.json()["message"] == "找不到執行紀錄 #missing"


@pytest.mark.asyncio
async def test_pipeline_runs_list_limit_over_max_returns_422(client: AsyncClient):
    """limit 超出上限不再靜默截斷，直接回 422（統一信封格式）。"""
    response = await client.get("/api/pipeline/runs?limit=500", headers=auth_headers())

    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert "limit" in body["message"]
    assert body["data"] is None


@pytest.mark.asyncio
async def test_pipeline_runs_list_limit_max_100_allowed(
    client: AsyncClient, db_session: AsyncSession
):
    db_session.add_all([_make_run(str(i)) for i in range(105)])
    await db_session.commit()

    response = await client.get("/api/pipeline/runs?limit=100", headers=auth_headers())

    assert response.status_code == 200
    assert len(response.json()["data"]) == 100


@pytest.mark.asyncio
async def test_triggered_by_literal_is_api(
    client: AsyncClient, db_session: AsyncSession
):
    mock_job = MagicMock()
    mock_job.id = "literal-job"
    mock_queue = MagicMock()
    mock_queue.enqueue.return_value = mock_job

    with (
        patch("ccas.api.routers.pipeline.Redis"),
        patch("ccas.api.routers.pipeline.Queue", return_value=mock_queue),
    ):
        response = await client.post("/api/pipeline/trigger", headers=auth_headers())

    run_id = response.json()["data"]["run_id"]
    row = (
        await db_session.execute(select(PipelineRun).where(PipelineRun.id == run_id))
    ).scalar_one()
    assert row.triggered_by == "api"
