"""Submission contract with committed SQLite state and replaceable queues."""

import sqlite3
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from rq import Retry
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ccas.pipeline.submission import (
    PipelineEnqueueError,
    RqPipelineQueue,
    submit_pipeline,
)
from ccas.pipeline.worker import on_failure_handler, run_pipeline_sync
from ccas.storage.models import (
    Base,
    PipelineRun,
    PipelineRunStatus,
    PipelineRunTerminalReason,
)


@pytest.fixture
async def submission_db(tmp_path: Path) -> AsyncIterator[tuple[AsyncSession, Path]]:
    path = tmp_path / "submission.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        yield session, path
    await engine.dispose()


class ObservingQueue:
    def __init__(self, path: Path, failure: Exception | None = None) -> None:
        self.path = path
        self.failure = failure
        self.params: dict[str, Any] | None = None

    def enqueue(self, params: dict[str, Any], *, run_id: str) -> str:
        # A separate connection models the worker seeing a committed run.
        with sqlite3.connect(self.path) as connection:
            row = connection.execute(
                "SELECT status, job_id FROM pipeline_runs WHERE id = ?", (run_id,)
            ).fetchone()
            assert row == ("queued", run_id)
            if self.failure:
                raise self.failure
            connection.execute(
                "UPDATE pipeline_runs SET status = 'running' WHERE id = ?", (run_id,)
            )
        self.params = params
        return "rq-submission-job"


@pytest.mark.parametrize("source", ["api", "scheduler"])
async def test_submission_commits_before_enqueue_and_preserves_worker_state(
    submission_db: tuple[AsyncSession, Path], source: str
) -> None:
    session, path = submission_db
    queue = ObservingQueue(path)
    result = await submit_pipeline(
        session, queue, {"bank_code": "CTBC", "force": True}, triggered_by=source
    )
    session.expire_all()
    run = await session.get(PipelineRun, result.run_id)
    assert run is not None
    assert run.job_id == result.job_id == "rq-submission-job"
    assert run.status == PipelineRunStatus.RUNNING
    assert run.triggered_by == source
    assert run.params == {"bank_code": "CTBC", "force": True}
    assert queue.params == {"bank_code": "CTBC", "force": True}


@pytest.mark.parametrize("source", ["api", "scheduler"])
async def test_submission_failure_persists_terminal_reason_and_preserves_cause(
    submission_db: tuple[AsyncSession, Path], source: str
) -> None:
    session, path = submission_db
    original = RuntimeError("queue unavailable")
    with pytest.raises(PipelineEnqueueError) as caught:
        await submit_pipeline(
            session, ObservingQueue(path, original), {}, triggered_by=source
        )
    session.expire_all()
    run = (await session.execute(select(PipelineRun))).scalar_one()
    assert run.id == caught.value.run_id
    assert run.status == PipelineRunStatus.FAILED
    assert run.terminal_reason == PipelineRunTerminalReason.ENQUEUE_FAILURE
    assert caught.value.cause is original
    assert run.error_message == (
        "Pipeline enqueue failed: queue unavailable"
        if source == "api"
        else "Pipeline enqueue failed (scheduler)"
    )


def test_rq_adapter_keeps_worker_retry_and_failure_callback_contract() -> None:
    queue = MagicMock()
    queue.enqueue.return_value.id = "rq-job"
    result = RqPipelineQueue(queue).enqueue({"bank_code": "CTBC"}, run_id="run-id")
    call = queue.enqueue.call_args
    assert result == "rq-job"
    assert call.args == (run_pipeline_sync, {"bank_code": "CTBC"})
    assert call.kwargs["run_id"] == "run-id"
    assert call.kwargs["on_failure"] is on_failure_handler
    assert call.kwargs["job_timeout"] == "30m"
    assert isinstance(call.kwargs["retry"], Retry)


async def test_initial_database_failure_never_enqueues(
    submission_db: tuple[AsyncSession, Path],
) -> None:
    session, path = submission_db
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TRIGGER reject_run BEFORE INSERT ON pipeline_runs "
            "BEGIN SELECT RAISE(ABORT, 'run persistence unavailable'); END"
        )
    queue = ObservingQueue(path)
    with pytest.raises(IntegrityError, match="run persistence unavailable"):
        await submit_pipeline(session, queue, {}, triggered_by="api")
    assert queue.params is None
    await session.rollback()
    assert (await session.execute(select(PipelineRun))).scalars().all() == []


async def test_job_id_write_failure_does_not_mark_accepted_job_rejected(
    submission_db: tuple[AsyncSession, Path],
) -> None:
    session, path = submission_db
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TRIGGER reject_job_id BEFORE UPDATE OF job_id ON pipeline_runs "
            "BEGIN SELECT RAISE(ABORT, 'job id persistence unavailable'); END"
        )
    queue = ObservingQueue(path)
    with pytest.raises(IntegrityError, match="job id persistence unavailable"):
        await submit_pipeline(session, queue, {}, triggered_by="api")
    assert queue.params == {}
    await session.rollback()
    run = (await session.execute(select(PipelineRun))).scalar_one()
    assert run.status == PipelineRunStatus.RUNNING
    assert run.terminal_reason is None
    assert run.job_id == run.id
