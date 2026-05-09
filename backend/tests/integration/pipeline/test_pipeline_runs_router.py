"""Pipeline runs API integration tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.storage.models import PipelineRun, PipelineRunStatus
from tests.integration.conftest import auth_headers


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
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_pipeline_runs_list_limit_is_capped(
    client: AsyncClient, db_session: AsyncSession
):
    db_session.add_all([_make_run(str(i)) for i in range(105)])
    await db_session.commit()

    response = await client.get("/api/pipeline/runs?limit=500", headers=auth_headers())

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
