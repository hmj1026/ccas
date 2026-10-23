"""Scheduler pipeline submission against isolated SQLite persistence."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from ccas.scheduler.jobs import trigger_pipeline_via_rq
from ccas.storage.models import (
    Base,
    PipelineRun,
    PipelineRunStatus,
    PipelineRunTerminalReason,
)


class _EngineDisposalProbe:
    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine
        self.dispose_calls = 0

    async def dispose(self) -> None:
        self.dispose_calls += 1
        await self.engine.dispose()


@dataclass
class _SchedulerDatabase:
    session_factory: async_sessionmaker[AsyncSession]
    disposal_probe: _EngineDisposalProbe


@pytest.fixture
async def _scheduler_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[_SchedulerDatabase]:
    database_path = tmp_path / "scheduler-pipeline.sqlite3"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{database_path}", poolclass=NullPool
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    disposal_probe = _EngineDisposalProbe(engine)
    monkeypatch.setattr(
        "ccas.storage.database.get_session_factory", lambda: session_factory
    )
    monkeypatch.setattr("ccas.storage.database.get_engine", lambda: disposal_probe)
    yield _SchedulerDatabase(session_factory, disposal_probe)
    await engine.dispose()


def _mock_scheduler_queue(
    monkeypatch: pytest.MonkeyPatch,
    *,
    job_id: str,
    enqueue_error: Exception | None = None,
) -> MagicMock:
    queue = MagicMock()
    if enqueue_error is None:
        queue.enqueue.return_value = SimpleNamespace(id=job_id)
    else:
        queue.enqueue.side_effect = enqueue_error

    monkeypatch.setattr(
        "ccas.scheduler.jobs.get_settings",
        lambda: SimpleNamespace(redis_url="redis://test.invalid/0"),
    )
    monkeypatch.setattr("ccas.scheduler.jobs.Redis.from_url", lambda _url: object())
    monkeypatch.setattr("ccas.scheduler.jobs.Queue", lambda **_kwargs: queue)
    return queue


async def _saved_runs(
    session_factory: async_sessionmaker[AsyncSession],
) -> list[PipelineRun]:
    async with session_factory() as session:
        result = await session.execute(select(PipelineRun))
        return list(result.scalars().all())


async def test_scheduler_enqueue_failure_persists_failed_run_and_disposes_engine(
    _scheduler_database: _SchedulerDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queue_error = RedisError("scheduler queue unavailable")
    _mock_scheduler_queue(
        monkeypatch,
        job_id="unused-job",
        enqueue_error=queue_error,
    )

    with pytest.raises(RedisError) as raised:
        await asyncio.to_thread(
            trigger_pipeline_via_rq,
            {"force": True, "bank_code": "CTBC"},
        )

    assert raised.value is queue_error
    runs = await _saved_runs(_scheduler_database.session_factory)
    assert len(runs) == 1
    assert runs[0].status == PipelineRunStatus.FAILED
    assert runs[0].terminal_reason == PipelineRunTerminalReason.ENQUEUE_FAILURE
    assert runs[0].triggered_by == "scheduler"
    assert runs[0].params == {"force": True, "bank_code": "CTBC"}
    assert _scheduler_database.disposal_probe.dispose_calls == 1


async def test_scheduler_submission_persists_queued_run_after_rq_accepts_job(
    _scheduler_database: _SchedulerDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opts = {"force": False, "bank_code": "ESUN", "year": 2026, "month": 6}
    queue = _mock_scheduler_queue(monkeypatch, job_id="rq-scheduler-job-123")

    returned_job_id = await asyncio.to_thread(trigger_pipeline_via_rq, opts)

    runs = await _saved_runs(_scheduler_database.session_factory)
    assert returned_job_id == "rq-scheduler-job-123"
    assert len(runs) == 1
    assert runs[0].status == PipelineRunStatus.QUEUED
    assert runs[0].triggered_by == "scheduler"
    assert runs[0].params == opts
    assert runs[0].job_id == returned_job_id
    assert runs[0].id == queue.enqueue.call_args.kwargs["run_id"]
    assert _scheduler_database.disposal_probe.dispose_calls == 1
