"""ProgressReporter 整合測試（pipeline-operations-center §2.5）。

涵蓋：
- ``NoopProgressReporter`` 不對 DB 產生任何寫入
- ``DbProgressReporter.stage_started`` 寫入 current_stage / total / processed=0
- ``DbProgressReporter.stage_item_done`` 250 ms 節流（短時間內多次呼叫只
  寫入第一筆）
- ``DbProgressReporter.stage_finished`` 不受節流影響，立即追加
  stage_summary、覆寫 current_stage_processed = current_stage_total
- 每筆寫入使用獨立 short-lived session（透過注入 instrumented session
  factory 統計 commit 次數）
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ccas.pipeline.progress import (
    DbProgressReporter,
    NoopProgressReporter,
)
from ccas.storage.models import Base, PipelineRun, PipelineRunStatus


@pytest.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
async def session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _seed_run(
    session_factory: async_sessionmaker[AsyncSession],
    run_id: str,
    **overrides: Any,
) -> None:
    async with session_factory() as session:
        run = PipelineRun(
            id=run_id,
            job_id=overrides.get("job_id", "job-1"),
            status=overrides.get("status", PipelineRunStatus.RUNNING),
            triggered_by=overrides.get("triggered_by", "api"),
            params=overrides.get("params", {}),
            stage_summary=overrides.get("stage_summary", []),
            created_at=overrides.get("created_at", datetime.now(UTC)),
            updated_at=overrides.get("updated_at", datetime.now(UTC)),
        )
        session.add(run)
        await session.commit()


async def _fetch_run(
    session_factory: async_sessionmaker[AsyncSession],
    run_id: str,
) -> PipelineRun:
    async with session_factory() as session:
        result = await session.execute(
            select(PipelineRun).where(PipelineRun.id == run_id)
        )
        row = result.scalar_one()
        # Detach so callers can read attributes after session close.
        await session.refresh(row)
        session.expunge(row)
        return row


async def test_noop_reporter_writes_nothing(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    run_id = str(uuid.uuid4())
    await _seed_run(session_factory, run_id)

    reporter = NoopProgressReporter()
    await reporter.stage_started("ingest", total=10)
    await reporter.stage_item_done("ingest", processed=5)
    await reporter.stage_finished("ingest", ok=10, fail=0, elapsed_ms=1234)

    row = await _fetch_run(session_factory, run_id)
    assert row.current_stage is None
    assert row.current_stage_processed == 0
    assert row.current_stage_total == 0
    assert row.stage_summary == []


async def test_db_reporter_stage_started_writes_total(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    run_id = str(uuid.uuid4())
    await _seed_run(session_factory, run_id)

    reporter = DbProgressReporter(run_id, session_factory)
    await reporter.stage_started("parse", total=120)

    row = await _fetch_run(session_factory, run_id)
    assert row.current_stage == "parse"
    assert row.current_stage_total == 120
    assert row.current_stage_processed == 0


async def test_db_reporter_throttles_high_frequency_item_done(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    run_id = str(uuid.uuid4())
    await _seed_run(session_factory, run_id)

    reporter = DbProgressReporter(run_id, session_factory, throttle_seconds=0.1)
    await reporter.stage_started("classify", total=50)

    # 50 calls within ~0.05s → should write at most 2 due to 100ms throttle.
    for i in range(1, 51):
        await reporter.stage_item_done("classify", processed=i)

    row = await _fetch_run(session_factory, run_id)
    # First call after stage_started always flushes (throttle reset).
    # Subsequent calls within 100ms window suppressed → processed reflects
    # an early item, NOT the final 50.
    assert row.current_stage == "classify"
    assert row.current_stage_processed < 50
    assert row.current_stage_processed >= 1


async def test_db_reporter_stage_finished_force_flushes(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    run_id = str(uuid.uuid4())
    await _seed_run(session_factory, run_id)

    reporter = DbProgressReporter(
        run_id, session_factory, throttle_seconds=10.0
    )  # huge throttle to prove finished bypasses it
    await reporter.stage_started("decrypt", total=5)
    # Hammer item_done so throttle suppresses subsequent calls.
    for i in range(1, 6):
        await reporter.stage_item_done("decrypt", processed=i)

    await reporter.stage_finished("decrypt", ok=5, fail=0, elapsed_ms=2500)

    row = await _fetch_run(session_factory, run_id)
    assert row.stage_summary == [
        {
            "stage": "decrypt",
            "ok": 5,
            "fail": 0,
            "elapsed_ms": 2500,
            "counts": {},
            "errors": [],
        }
    ]
    # current_stage_processed overwritten to current_stage_total per spec.
    assert row.current_stage_processed == 5
    assert row.current_stage_total == 5


async def test_db_reporter_stage_finished_appends_multiple_stages(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    run_id = str(uuid.uuid4())
    await _seed_run(session_factory, run_id)

    reporter = DbProgressReporter(run_id, session_factory)
    await reporter.stage_started("ingest", total=2)
    await reporter.stage_finished(
        "ingest",
        ok=2,
        fail=0,
        elapsed_ms=100,
        counts={"staged": 2, "failed": 0},
    )
    await reporter.stage_started("decrypt", total=2)
    await reporter.stage_finished(
        "decrypt",
        ok=1,
        fail=1,
        elapsed_ms=200,
        counts={"decrypted": 1, "failed": 1},
        errors=["bad password"],
    )

    row = await _fetch_run(session_factory, run_id)
    assert row.stage_summary == [
        {
            "stage": "ingest",
            "ok": 2,
            "fail": 0,
            "elapsed_ms": 100,
            "counts": {"staged": 2, "failed": 0},
            "errors": [],
        },
        {
            "stage": "decrypt",
            "ok": 1,
            "fail": 1,
            "elapsed_ms": 200,
            "counts": {"decrypted": 1, "failed": 1},
            "errors": ["bad password"],
        },
    ]


async def test_db_reporter_uses_independent_session_per_call(
    engine: AsyncEngine,
) -> None:
    # Wrap the session factory to count how many sessions get opened.
    base_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    open_count = 0

    class CountingFactory:
        def __call__(self) -> AsyncSession:
            nonlocal open_count
            open_count += 1
            return base_factory()

    counting_factory = CountingFactory()

    run_id = str(uuid.uuid4())
    async with base_factory() as session:
        run = PipelineRun(
            id=run_id,
            job_id="job-1",
            status=PipelineRunStatus.RUNNING,
            triggered_by="api",
            params={},
            stage_summary=[],
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        session.add(run)
        await session.commit()

    reporter = DbProgressReporter(run_id, counting_factory, throttle_seconds=0.0)
    open_count = 0  # reset after seed
    await reporter.stage_started("parse", total=3)
    await reporter.stage_item_done("parse", processed=1)
    await reporter.stage_finished("parse", ok=3, fail=0, elapsed_ms=42)

    # Each hook opens its own session: started + item_done + finished = 3.
    assert open_count == 3


async def test_db_reporter_stage_finished_handles_missing_row(
    session_factory: async_sessionmaker[AsyncSession],
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Reporter targets a run_id that does not exist; should not raise,
    # only log warning.
    reporter = DbProgressReporter("missing-run-id", session_factory)
    await reporter.stage_finished("ingest", ok=0, fail=0, elapsed_ms=0)

    assert any(
        "pipeline_runs row missing-run-id not found" in rec.message
        for rec in caplog.records
    )


async def test_db_reporter_throttle_resets_on_new_stage(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    run_id = str(uuid.uuid4())
    await _seed_run(session_factory, run_id)

    reporter = DbProgressReporter(run_id, session_factory, throttle_seconds=10.0)
    await reporter.stage_started("ingest", total=5)
    await reporter.stage_item_done("ingest", processed=1)  # flushes

    # Without reset, this would be suppressed by 10s window.
    await reporter.stage_started("decrypt", total=8)
    await reporter.stage_item_done("decrypt", processed=1)  # should flush

    row = await _fetch_run(session_factory, run_id)
    assert row.current_stage == "decrypt"
    assert row.current_stage_processed == 1
    assert row.current_stage_total == 8


async def test_db_reporter_stage_finished_retries_on_database_locked(
    session_factory: async_sessionmaker[AsyncSession],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Issue #6: when ``stage_finished`` hits ``database is locked`` (e.g.
    scheduler heartbeat + backend GET both contending on the WAL), the
    reporter must retry with backoff instead of letting the exception
    propagate and stranding the run at status='running'. After the retry
    succeeds, the row's ``stage_summary`` must contain the entry exactly
    once and ``current_stage_processed == current_stage_total``.
    """
    import logging

    from sqlalchemy.exc import OperationalError

    run_id = str(uuid.uuid4())
    await _seed_run(session_factory, run_id)

    # Toggle: only inject failures after stage_started has populated
    # current_stage_total. Without this, the first two stage_started
    # commits would be the ones that fail and the test would never get
    # to exercise stage_finished.
    inject_failures = False
    call_count = 0

    class FlakyFactory:
        def __call__(self) -> AsyncSession:
            nonlocal call_count
            session = session_factory()
            if inject_failures:
                call_count += 1
                if call_count <= 2:
                    # Monkey-patch the bound commit so the failure path runs
                    # exactly once per failing attempt. The session is
                    # discarded immediately after — DbProgressReporter opens
                    # a fresh session for the retry — so the dirty post-fail
                    # state is never observed by the next iteration.
                    async def failing_commit() -> None:
                        raise OperationalError(
                            "UPDATE pipeline_runs SET ...",
                            {},
                            Exception("database is locked"),
                        )

                    session.commit = failing_commit  # type: ignore[method-assign]
            return session

    flaky_factory = FlakyFactory()

    reporter = DbProgressReporter(run_id, flaky_factory)
    # First populate current_stage_total via a real stage_started.
    await reporter.stage_started("ingest", total=131)
    inject_failures = True

    with caplog.at_level(logging.WARNING, logger="ccas.pipeline.progress"):
        await reporter.stage_finished(
            "ingest",
            ok=130,
            fail=1,
            elapsed_ms=66104,
            counts={"messages": 131, "attachments": 130},
            errors=["one parse error"],
        )

    # Three attempts: two locked + one success
    assert call_count == 3

    # Retry warnings should be logged with structured extras so operators
    # can filter on run_id / stage in production JSON logs.
    retry_records = [
        rec
        for rec in caplog.records
        if "database-locked" in rec.getMessage()
        and getattr(rec, "run_id", None) == run_id
        and getattr(rec, "attempt", None) is not None
    ]
    assert retry_records, (
        "expected at least one retry warning log with run_id/attempt extras "
        "when stage_finished hits database-is-locked"
    )

    # Final row state must be consistent — entry written exactly once
    row = await _fetch_run(session_factory, run_id)
    assert len(row.stage_summary) == 1, (
        "stage_summary must contain exactly one entry; retry must not double-append"
    )
    assert row.stage_summary[0]["stage"] == "ingest"
    assert row.stage_summary[0]["ok"] == 130
    assert row.stage_summary[0]["fail"] == 1
    assert row.current_stage_processed == row.current_stage_total == 131


async def test_db_reporter_stage_finished_gives_up_after_max_retries(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """If the lock persists past the retry budget, raise so the worker can
    surface the failure (no silent swallow). Issue #6 expects retries to
    cover transient contention, not permanent lock holders.
    """
    from sqlalchemy.exc import OperationalError

    run_id = str(uuid.uuid4())
    await _seed_run(session_factory, run_id)

    inject_failures = False

    class AlwaysLockedFactory:
        def __call__(self) -> AsyncSession:
            session = session_factory()
            if inject_failures:

                async def failing_commit() -> None:
                    raise OperationalError(
                        "UPDATE pipeline_runs",
                        {},
                        Exception("database is locked"),
                    )

                session.commit = failing_commit  # type: ignore[method-assign]
            return session

    reporter = DbProgressReporter(run_id, AlwaysLockedFactory())
    await reporter.stage_started("ingest", total=10)
    inject_failures = True

    with pytest.raises(OperationalError, match="database is locked"):
        await reporter.stage_finished("ingest", ok=10, fail=0, elapsed_ms=100)


async def test_db_reporter_lock_serializes_concurrent_item_done(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    run_id = str(uuid.uuid4())
    await _seed_run(session_factory, run_id)

    reporter = DbProgressReporter(run_id, session_factory, throttle_seconds=0.05)
    await reporter.stage_started("classify", total=100)

    # Concurrent gather — lock should serialize and most calls suppressed.
    await asyncio.gather(
        *[reporter.stage_item_done("classify", processed=i) for i in range(1, 21)]
    )

    row = await _fetch_run(session_factory, run_id)
    # Should not raise; processed should be > 0 and <= 20.
    assert 1 <= row.current_stage_processed <= 20
