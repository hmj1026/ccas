"""Worker integration with pipeline_runs status tracking."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from rq.job import Job
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ccas.pipeline.summary import PipelineSummary, StageSummary
from ccas.pipeline.worker import (
    mark_manual_review,
    on_failure_handler,
    run_pipeline_sync,
)
from ccas.storage.models import (
    Base,
    PipelineRun,
    PipelineRunStatus,
    StagedAttachment,
    StagedAttachmentStatus,
)


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

        async def fake_run_pipeline(
            session, options, progress_reporter=None, *, notify_job
        ):
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


async def _insert_staged(
    session_factory,
    *,
    bank_code: str,
    status: str = StagedAttachmentStatus.STAGED,
    message_id: str,
) -> None:
    from datetime import UTC, datetime

    async with session_factory() as session:
        session.add(
            StagedAttachment(
                bank_code=bank_code,
                gmail_message_id=message_id,
                gmail_attachment_id=f"att-{message_id}",
                gmail_part_id="1",
                message_date=datetime.now(UTC),
                original_filename=f"{message_id}.pdf",
                status=status,
            )
        )
        await session.commit()


async def _get_staged_statuses(session_factory) -> dict[str, str]:
    from sqlalchemy import select

    async with session_factory() as session:
        rows = (await session.execute(select(StagedAttachment))).scalars().all()
        return {row.gmail_message_id: row.status for row in rows}


class TestRunPipelineSyncFailurePath:
    def test_marks_run_failed_when_run_pipeline_raises(
        self,
        worker_db,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """run_pipeline 拋例外時 PipelineRun 必須是 FAILED 而非 RUNNING。"""
        asyncio.run(_insert_run(worker_db))

        async def boom(session, options, progress_reporter=None, *, notify_job):
            raise RuntimeError("pipeline exploded")

        monkeypatch.setattr("ccas.pipeline.orchestrator.run_pipeline", boom)

        with pytest.raises(RuntimeError, match="pipeline exploded"):
            run_pipeline_sync({}, run_id="run-1")

        run = asyncio.run(_get_run(worker_db))
        assert run.status == PipelineRunStatus.FAILED
        assert run.error_message is not None
        assert "RuntimeError" in run.error_message

    def test_marks_run_failed_when_classify_batch_commit_fails(
        self,
        worker_db,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """classify 整批 commit 失敗（orchestrator 吞成 failed 階段）時，
        PipelineRun 必須是 FAILED，而非因 run_pipeline 正常回傳而誤標 SUCCEEDED。
        """
        asyncio.run(_insert_run(worker_db))

        async def fake_run_pipeline(
            session, options, progress_reporter=None, *, notify_job
        ):
            # 模擬 orchestrator._run_stage 捕捉 ClassifyError 後的階段摘要：
            # classify 整批 rollback，counts 只剩 failed。
            return PipelineSummary(
                stages=(
                    StageSummary(stage="ingest", counts={"staged": 2, "failed": 0}),
                    StageSummary(
                        stage="classify",
                        counts={"failed": 1},
                        errors=["ClassifyError: 分類結果寫入失敗"],
                    ),
                ),
                total_seconds=0.1,
            )

        monkeypatch.setattr(
            "ccas.pipeline.orchestrator.run_pipeline", fake_run_pipeline
        )

        result = run_pipeline_sync({}, run_id="run-1")

        run = asyncio.run(_get_run(worker_db))
        assert run.status == PipelineRunStatus.FAILED
        assert run.error_message is not None
        assert "classify" in run.error_message
        # result 仍須回傳給 RQ job result（不 re-raise）
        assert result["total_seconds"] == 0.1

    def test_marks_run_succeeded_when_classify_has_zero_to_classify(
        self,
        worker_db,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """classify 沒有可分類交易（成功路徑 counts={'classified': 0}）時，
        不得誤判為失敗——必須維持 SUCCEEDED。"""
        asyncio.run(_insert_run(worker_db))

        async def fake_run_pipeline(
            session, options, progress_reporter=None, *, notify_job
        ):
            return PipelineSummary(
                stages=(StageSummary(stage="classify", counts={"classified": 0}),),
                total_seconds=0.1,
            )

        monkeypatch.setattr(
            "ccas.pipeline.orchestrator.run_pipeline", fake_run_pipeline
        )

        run_pipeline_sync({}, run_id="run-1")

        run = asyncio.run(_get_run(worker_db))
        assert run.status == PipelineRunStatus.SUCCEEDED
        assert run.error_message is None


class TestMarkManualReviewScope:
    def test_bank_code_scopes_update(self, worker_db):
        asyncio.run(_insert_staged(worker_db, bank_code="CTBC", message_id="msg-ctbc"))
        asyncio.run(_insert_staged(worker_db, bank_code="ESUN", message_id="msg-esun"))

        async def _mark() -> int:
            async with worker_db() as session:
                return await mark_manual_review(session, bank_code="CTBC")

        count = asyncio.run(_mark())

        statuses = asyncio.run(_get_staged_statuses(worker_db))
        assert count == 1
        assert statuses["msg-ctbc"] == StagedAttachmentStatus.MANUAL_REVIEW_NEEDED
        assert statuses["msg-esun"] == StagedAttachmentStatus.STAGED

    def test_no_bank_code_updates_all(self, worker_db):
        asyncio.run(_insert_staged(worker_db, bank_code="CTBC", message_id="msg-ctbc"))
        asyncio.run(
            _insert_staged(
                worker_db,
                bank_code="ESUN",
                status=StagedAttachmentStatus.DECRYPTED,
                message_id="msg-esun",
            )
        )

        async def _mark() -> int:
            async with worker_db() as session:
                return await mark_manual_review(session)

        count = asyncio.run(_mark())

        statuses = asyncio.run(_get_staged_statuses(worker_db))
        assert count == 2
        assert all(
            s == StagedAttachmentStatus.MANUAL_REVIEW_NEEDED for s in statuses.values()
        )


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

    def test_passes_bank_code_from_job_args_to_mark_manual_review(
        self,
        worker_db,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """opts 以第一個位置參數 enqueue，bank_code 必須傳入 mark_manual_review。"""
        asyncio.run(_insert_run(worker_db))
        mark_mock = AsyncMock(return_value=0)
        monkeypatch.setattr("ccas.pipeline.worker.mark_manual_review", mark_mock)
        job = MagicMock(spec=Job)
        job.id = "job-1"
        job.retries_left = 0
        job.args = ({"bank_code": "CTBC", "force": False},)
        job.kwargs = {"run_id": "run-1"}

        on_failure_handler(job, MagicMock(), RuntimeError, RuntimeError("boom"), None)

        mark_mock.assert_awaited_once()
        assert mark_mock.await_args is not None
        assert mark_mock.await_args.kwargs.get("bank_code") == "CTBC"

    def test_run_still_marked_failed_when_manual_review_marking_raises(
        self,
        worker_db,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """步驟隔離：mark_manual_review 失敗不得阻斷 mark_pipeline_run_failed。"""
        asyncio.run(_insert_run(worker_db))
        monkeypatch.setattr(
            "ccas.pipeline.worker.mark_manual_review",
            AsyncMock(side_effect=RuntimeError("db locked")),
        )
        job = MagicMock(spec=Job)
        job.id = "job-1"
        job.retries_left = 0
        job.args = ()
        job.kwargs = {"run_id": "run-1"}

        on_failure_handler(
            job, MagicMock(), TimeoutError, TimeoutError("job timeout"), None
        )

        run = asyncio.run(_get_run(worker_db))
        assert run.status == PipelineRunStatus.FAILED
        assert run.error_message is not None
