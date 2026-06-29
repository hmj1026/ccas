"""RQ worker 與重試邏輯的單元測試。

涵蓋重試設定、狀態標記函式、失敗分類、run_pipeline_sync 內部協程
（以真實 asyncio.run 執行）、bank_code 解析與 on_failure_handler。
"""

from __future__ import annotations

import contextlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ccas.pipeline.summary import PipelineSummary, StageSummary
from ccas.pipeline.worker import (
    MAX_RETRIES,
    _calculate_retry_delays,
    _classify_batch_failed,
    _extract_bank_code,
    _run_failure_reason,
    get_retry,
    mark_manual_review,
    mark_pipeline_run_failed,
    mark_pipeline_run_running,
    mark_pipeline_run_succeeded,
    on_failure_handler,
    run_pipeline_sync,
)


class _FakeSession:
    """Async-context-manager session stub with awaitable execute/commit/get."""

    def __init__(self) -> None:
        self.execute = AsyncMock()
        self.commit = AsyncMock()
        self.get = AsyncMock()

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False


class TestRetryConfig:
    """驗證重試延遲計算與 RQ Retry 設定。"""

    def test_retry_delays_are_exponential(self):
        delays = _calculate_retry_delays()
        assert delays == [1, 2, 4]

    def test_retry_delays_capped_at_60(self):
        """即使超過 60 也應被 cap。"""
        # 目前只有 3 次所以不會超過，但驗證邏輯正確
        delays = _calculate_retry_delays()
        assert all(d <= 60 for d in delays)

    def test_max_retries_is_three(self):
        assert MAX_RETRIES == 3

    def test_get_retry_returns_retry_object(self):
        retry = get_retry()
        assert retry.max == MAX_RETRIES
        assert retry.intervals == [1, 2, 4]


class TestMarkStatusFunctions:
    """直接覆蓋 _set_pipeline_run_status 與三個狀態標記函式。"""

    async def test_mark_running(self):
        session = AsyncMock()
        await mark_pipeline_run_running(session, "run-1")
        session.execute.assert_awaited_once()
        session.commit.assert_awaited_once()

    async def test_mark_succeeded(self):
        session = AsyncMock()
        await mark_pipeline_run_succeeded(session, "run-1")
        session.execute.assert_awaited_once()
        session.commit.assert_awaited_once()

    async def test_mark_failed(self):
        session = AsyncMock()
        await mark_pipeline_run_failed(session, "run-1", "boom")
        session.execute.assert_awaited_once()
        session.commit.assert_awaited_once()


class TestFailureClassification:
    """驗證 _classify_batch_failed 與 _run_failure_reason 的判定。"""

    def test_classify_batch_failed_true(self):
        summary = PipelineSummary(
            stages=(StageSummary(stage="classify", counts={"failed": 2}),),
            total_seconds=1.0,
        )
        assert _classify_batch_failed(summary) is True

    def test_classify_batch_failed_false_on_success_counts(self):
        summary = PipelineSummary(
            stages=(StageSummary(stage="classify", counts={"classified": 5}),),
            total_seconds=1.0,
        )
        assert _classify_batch_failed(summary) is False

    def test_run_failure_reason_classify(self):
        summary = PipelineSummary(
            stages=(StageSummary(stage="classify", counts={"failed": 1}),),
            total_seconds=1.0,
        )
        reason = _run_failure_reason(summary)
        assert reason is not None
        assert "classify" in reason

    def test_run_failure_reason_stage_error(self):
        summary = PipelineSummary(
            stages=(StageSummary(stage="ingest", counts={}, errors=["page 2 failed"]),),
            total_seconds=1.0,
        )
        reason = _run_failure_reason(summary)
        assert reason is not None
        assert "ingest" in reason
        assert "page 2 failed" in reason

    def test_run_failure_reason_ignores_notify_errors(self):
        summary = PipelineSummary(
            stages=(
                StageSummary(stage="notify", counts={}, errors=["telegram timeout"]),
            ),
            total_seconds=1.0,
        )
        assert _run_failure_reason(summary) is None

    def test_run_failure_reason_success(self):
        summary = PipelineSummary(
            stages=(StageSummary(stage="parse", counts={"parsed": 3}),),
            total_seconds=1.0,
        )
        assert _run_failure_reason(summary) is None


@contextlib.contextmanager
def _patched_pipeline_env(*, result=None, run_pipeline_exc=None, mark_failed_exc=None):
    """Patch run_pipeline_sync 依賴，讓內部 _run 協程可以真實執行。

    Yields a namespace exposing the patched mark_* AsyncMocks so callers
    can assert which state-transition path executed.
    """
    session = _FakeSession()
    with contextlib.ExitStack() as stack:
        from_dict = stack.enter_context(
            patch("ccas.pipeline.options.PipelineOptions.from_dict")
        )
        from_dict.return_value = MagicMock()

        get_sf = stack.enter_context(
            patch("ccas.storage.database.get_session_factory", new_callable=MagicMock)
        )
        get_sf.return_value = lambda: session

        get_engine = stack.enter_context(
            patch("ccas.storage.database.get_engine", new_callable=MagicMock)
        )
        get_engine.return_value.dispose = AsyncMock()

        run_pipeline = stack.enter_context(
            patch("ccas.pipeline.orchestrator.run_pipeline", new_callable=AsyncMock)
        )
        if run_pipeline_exc is not None:
            run_pipeline.side_effect = run_pipeline_exc
        else:
            run_pipeline.return_value = result

        running = stack.enter_context(
            patch(
                "ccas.pipeline.worker.mark_pipeline_run_running",
                new_callable=AsyncMock,
            )
        )
        succeeded = stack.enter_context(
            patch(
                "ccas.pipeline.worker.mark_pipeline_run_succeeded",
                new_callable=AsyncMock,
            )
        )
        failed = stack.enter_context(
            patch(
                "ccas.pipeline.worker.mark_pipeline_run_failed",
                new_callable=AsyncMock,
            )
        )
        if mark_failed_exc is not None:
            failed.side_effect = mark_failed_exc

        yield SimpleNamespace(
            session=session,
            run_pipeline=run_pipeline,
            running=running,
            succeeded=succeeded,
            failed=failed,
        )


class TestRunPipelineSyncExecution:
    """以真實 asyncio.run 執行內部 _run 協程，覆蓋狀態轉換分支。"""

    def test_run_id_success_marks_succeeded(self):
        summary = PipelineSummary(
            stages=(StageSummary(stage="ingest", counts={"downloaded": 2}),),
            total_seconds=2.0,
        )
        with _patched_pipeline_env(result=summary) as env:
            result = run_pipeline_sync({"bank_code": "CTBC"}, run_id="run-1")

        env.running.assert_awaited_once()
        env.succeeded.assert_awaited_once()
        env.failed.assert_not_awaited()
        assert result["total_seconds"] == 2.0
        assert result["stages"][0]["stage"] == "ingest"

    def test_run_id_failure_reason_marks_failed(self):
        summary = PipelineSummary(
            stages=(StageSummary(stage="parse", counts={}, errors=["boom"]),),
            total_seconds=1.0,
        )
        with _patched_pipeline_env(result=summary) as env:
            result = run_pipeline_sync({}, run_id="run-2")

        env.failed.assert_awaited_once()
        env.succeeded.assert_not_awaited()
        # 不 re-raise，仍回傳序列化摘要
        assert result["stages"][0]["errors"] == ["boom"]

    def test_run_id_classify_batch_failed_marks_failed(self):
        summary = PipelineSummary(
            stages=(StageSummary(stage="classify", counts={"failed": 1}),),
            total_seconds=1.0,
        )
        with _patched_pipeline_env(result=summary) as env:
            run_pipeline_sync({}, run_id="run-3")

        env.failed.assert_awaited_once()
        env.succeeded.assert_not_awaited()

    def test_no_run_id_skips_status_marks(self):
        summary = PipelineSummary(stages=(), total_seconds=0.5)
        with _patched_pipeline_env(result=summary) as env:
            result = run_pipeline_sync(None)

        env.running.assert_not_awaited()
        env.succeeded.assert_not_awaited()
        env.failed.assert_not_awaited()
        assert result["total_seconds"] == 0.5
        assert result["stages"] == []
        assert result["failures"] == []

    def test_run_pipeline_raises_marks_failed_and_reraises(self):
        with _patched_pipeline_env(run_pipeline_exc=RuntimeError("kaboom")) as env:
            with pytest.raises(RuntimeError, match="kaboom"):
                run_pipeline_sync({}, run_id="run-4")

        env.failed.assert_awaited_once()
        env.succeeded.assert_not_awaited()

    def test_run_pipeline_raises_no_run_id_reraises(self):
        with _patched_pipeline_env(run_pipeline_exc=RuntimeError("nope")) as env:
            with pytest.raises(RuntimeError, match="nope"):
                run_pipeline_sync(None)

        env.failed.assert_not_awaited()

    def test_mark_failed_error_is_logged_and_original_reraised(self):
        # run_pipeline 失敗 + mark_failed 自身亦拋例外 → 記錄 log 並 re-raise 原例外
        with _patched_pipeline_env(
            run_pipeline_exc=RuntimeError("primary"),
            mark_failed_exc=Exception("db down"),
        ) as env:
            with pytest.raises(RuntimeError, match="primary"):
                run_pipeline_sync({}, run_id="run-5")

        env.failed.assert_awaited_once()


class TestMarkManualReview:
    """驗證 mark_manual_review 的 SQL 更新邏輯與 bank_code 過濾分支。"""

    async def test_executes_update_and_commits(self):
        mock_result = MagicMock()
        mock_result.rowcount = 3
        session = AsyncMock()
        session.execute.return_value = mock_result

        count = await mark_manual_review(session)

        assert count == 3
        session.execute.assert_awaited_once()
        session.commit.assert_awaited_once()

    async def test_with_bank_code_filter(self):
        mock_result = MagicMock()
        mock_result.rowcount = 1
        session = AsyncMock()
        session.execute.return_value = mock_result

        count = await mark_manual_review(session, bank_code="CTBC")

        assert count == 1
        session.execute.assert_awaited_once()
        session.commit.assert_awaited_once()


class TestExtractBankCode:
    """驗證 _extract_bank_code 從 RQ job 取出 bank_code 的各分支。"""

    def test_from_kwargs_opts(self):
        job = MagicMock()
        job.kwargs = {"opts": {"bank_code": "CTBC"}}
        assert _extract_bank_code(job) == "CTBC"

    def test_from_positional_args(self):
        job = MagicMock()
        job.kwargs = {}
        job.args = ({"bank_code": "ESUN"},)
        assert _extract_bank_code(job) == "ESUN"

    def test_opts_not_dict(self):
        job = MagicMock()
        job.kwargs = {"opts": "not-a-dict"}
        job.args = ()
        assert _extract_bank_code(job) is None

    def test_bank_code_not_str(self):
        job = MagicMock()
        job.kwargs = {"opts": {"bank_code": 123}}
        assert _extract_bank_code(job) is None

    def test_no_opts_no_args(self):
        job = MagicMock(spec=[])  # no kwargs / args attributes
        assert _extract_bank_code(job) is None


@contextlib.contextmanager
def _patched_failure_env(*, mark_review_exc=None, mark_failed_exc=None, review_count=4):
    """Patch on_failure_handler 依賴，讓內部 _mark 協程可以真實執行。"""
    session = _FakeSession()
    with contextlib.ExitStack() as stack:
        get_sf = stack.enter_context(
            patch("ccas.storage.database.get_session_factory", new_callable=MagicMock)
        )
        get_sf.return_value = lambda: session

        get_engine = stack.enter_context(
            patch("ccas.storage.database.get_engine", new_callable=MagicMock)
        )
        get_engine.return_value.dispose = AsyncMock()

        review = stack.enter_context(
            patch("ccas.pipeline.worker.mark_manual_review", new_callable=AsyncMock)
        )
        if mark_review_exc is not None:
            review.side_effect = mark_review_exc
        else:
            review.return_value = review_count

        failed = stack.enter_context(
            patch(
                "ccas.pipeline.worker.mark_pipeline_run_failed",
                new_callable=AsyncMock,
            )
        )
        if mark_failed_exc is not None:
            failed.side_effect = mark_failed_exc

        yield SimpleNamespace(review=review, failed=failed)


class TestOnFailureHandlerSkip:
    """重試尚未耗盡時不應觸發標記。"""

    def test_skips_when_retries_remaining(self):
        job = MagicMock()
        job.retries_left = 2
        with patch("ccas.pipeline.worker.asyncio.run") as mock_run:
            on_failure_handler(
                job, MagicMock(), RuntimeError, RuntimeError("boom"), None
            )
            mock_run.assert_not_called()


class TestOnFailureHandlerExecution:
    """以真實 asyncio.run 執行 _mark，覆蓋標記分支。"""

    def test_marks_review_and_run_failed(self):
        job = MagicMock()
        job.id = "job-1"
        job.retries_left = 0
        job.kwargs = {"run_id": "run-1", "opts": {"bank_code": "CTBC"}}

        with _patched_failure_env() as env:
            on_failure_handler(
                job, MagicMock(), RuntimeError, RuntimeError("boom"), None
            )

        env.review.assert_awaited_once()
        assert env.review.await_args.kwargs["bank_code"] == "CTBC"
        env.failed.assert_awaited_once()

    def test_no_retries_attr_triggers_mark(self):
        job = MagicMock(spec=["id", "kwargs"])
        job.id = "job-2"
        job.kwargs = {"run_id": "run-2"}

        with _patched_failure_env() as env:
            on_failure_handler(
                job, MagicMock(), RuntimeError, RuntimeError("boom"), None
            )

        env.review.assert_awaited_once()
        env.failed.assert_awaited_once()

    def test_review_error_does_not_block_run_failed(self):
        job = MagicMock()
        job.id = "job-3"
        job.retries_left = 0
        job.kwargs = {"run_id": "run-3"}

        with _patched_failure_env(
            mark_review_exc=RuntimeError("review db down")
        ) as env:
            on_failure_handler(
                job, MagicMock(), RuntimeError, RuntimeError("boom"), None
            )

        env.failed.assert_awaited_once()

    def test_run_failed_error_is_logged(self):
        job = MagicMock()
        job.id = "job-4"
        job.retries_left = 0
        job.kwargs = {"run_id": "run-4"}

        with _patched_failure_env(mark_failed_exc=RuntimeError("run db down")) as env:
            # 不應拋出（內部捕捉並記錄）
            on_failure_handler(
                job, MagicMock(), RuntimeError, RuntimeError("boom"), None
            )

        env.review.assert_awaited_once()
        env.failed.assert_awaited_once()

    def test_no_run_id_skips_run_failed(self):
        job = MagicMock()
        job.id = "job-5"
        job.retries_left = 0
        job.kwargs = {"opts": {"bank_code": "ESUN"}}

        with _patched_failure_env() as env:
            on_failure_handler(
                job, MagicMock(), RuntimeError, RuntimeError("boom"), None
            )

        env.review.assert_awaited_once()
        env.failed.assert_not_awaited()
