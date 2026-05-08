"""Worker integration with pipeline_runs status tracking."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from rq.job import Job
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ccas.pipeline.summary import PipelineSummary, StageSummary
from ccas.pipeline.worker import on_failure_handler, run_pipeline_sync
from ccas.storage.models import Base, PipelineRun, PipelineRunStatus


@pytest.fixture
def worker_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "worker.sqlite3"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async def _create_schema() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_create_schema())

    monkeypatch.setattr(
        "ccas.storage.database.get_session_factory", lambda: session_factory
    )
    monkeypatch.setattr("ccas.storage.database.get_engine", lambda: engine)

    yield session_factory

    asyncio.run(engine.dispose())


async def _insert_run(session_factory, *, run_id: str = "run-1") -> None:
    async with session_factory() as session:
        session.add(
            PipelineRun(
                id=run_id,
                job_id="job-1",
                status=PipelineRunStatus.QUEUED,
                triggered_by="api",
                params={},
                stage_summary=[],
            )
        )
        await session.commit()


async def _get_run(session_factory, run_id: str = "run-1") -> PipelineRun:
    async with session_factory() as session:
        run = await session.get(PipelineRun, run_id)
        assert run is not None
        return run


class TestRunPipelineSyncPipelineRunStatus:
    def test_marks_run_running_then_succeeded_and_uses_db_reporter(
        self,
        worker_db,
        monkeypatch: pytest.MonkeyPatch,
    ):
        asyncio.run(_insert_run(worker_db))
        seen = {}

        async def fake_run_pipeline(session, options, progress_reporter=None):
            assert progress_reporter is not None
            seen["progress_reporter"] = progress_reporter
            await progress_reporter.stage_started("ingest", 1)
            return PipelineSummary(
                stages=(
                    StageSummary(
                        stage="ingest",
                        counts={"downloaded": 1, "failed": 0},
                    ),
                ),
                total_seconds=0.25,
            )

        monkeypatch.setattr(
            "ccas.pipeline.orchestrator.run_pipeline", fake_run_pipeline
        )

        result = run_pipeline_sync({"bank_code": "CTBC"}, run_id="run-1")

        run = asyncio.run(_get_run(worker_db))
        assert result["total_seconds"] == 0.25
        assert run.status == PipelineRunStatus.SUCCEEDED
        assert run.started_at is not None
        assert run.completed_at is not None
        assert run.error_message is None
        assert run.current_stage == "ingest"
        assert run.current_stage_total == 1
        assert seen["progress_reporter"].__class__.__name__ == "DbProgressReporter"


class TestOnFailureHandlerPipelineRunStatus:
    def test_marks_pipeline_run_failed_from_job_kwargs(
        self,
        worker_db,
        monkeypatch: pytest.MonkeyPatch,
    ):
        asyncio.run(_insert_run(worker_db))
        monkeypatch.setattr(
            "ccas.pipeline.worker.mark_manual_review",
            AsyncMock(return_value=0),
        )
        job = MagicMock(spec=Job)
        job.id = "job-1"
        job.retries_left = 0
        job.kwargs = {"run_id": "run-1"}

        on_failure_handler(
            job,
            MagicMock(),
            TimeoutError,
            TimeoutError("job timeout after 30m"),
            None,
        )

        run = asyncio.run(_get_run(worker_db))
        assert run.status == PipelineRunStatus.FAILED
        assert run.completed_at is not None
        assert run.error_message is not None
        assert "timeout" in run.error_message.lower()
