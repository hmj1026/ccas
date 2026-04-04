"""Pipeline worker 進階測試：run_pipeline_sync、mark_manual_review、on_failure_handler。

補強 worker.py 的覆蓋率（35% -> 80%+）。
"""

from unittest.mock import AsyncMock, MagicMock, patch

from ccas.pipeline.summary import FailedItem, PipelineSummary, StageSummary
from ccas.pipeline.worker import (
    mark_manual_review,
    on_failure_handler,
    run_pipeline_sync,
)


def _make_summary() -> PipelineSummary:
    """建立測試用 PipelineSummary。"""
    return PipelineSummary(
        stages=(
            StageSummary(stage="ingest", counts={"downloaded": 2}),
            StageSummary(stage="parse", counts={"parsed": 2}, errors=["warn"]),
        ),
        total_seconds=1.5,
        failures=(FailedItem(item_id="att-1", error="parse failed"),),
    )


class TestRunPipelineSync:
    """驗證 run_pipeline_sync 的序列化與呼叫邏輯。

    run_pipeline_sync 使用 lazy import（函式內 import），
    需 patch 原始模組路徑而非 worker 模組屬性。
    """

    @patch("ccas.pipeline.worker.asyncio.run")
    @patch("ccas.storage.database.get_engine", new_callable=MagicMock)
    @patch("ccas.storage.database.get_session_factory", new_callable=MagicMock)
    @patch("ccas.pipeline.orchestrator.run_pipeline", new_callable=MagicMock)
    @patch("ccas.pipeline.options.PipelineOptions.from_dict")
    def test_returns_serialized_summary(
        self, mock_from_dict, mock_run, mock_sf, mock_engine, mock_asyncio_run
    ):
        summary = _make_summary()
        mock_asyncio_run.return_value = summary
        mock_from_dict.return_value = MagicMock()

        result = run_pipeline_sync({"force": True, "bank_code": "CTBC"})

        mock_from_dict.assert_called_once_with(
            {"force": True, "bank_code": "CTBC"}
        )
        assert result["total_seconds"] == 1.5
        assert len(result["stages"]) == 2
        assert result["stages"][0]["stage"] == "ingest"
        assert result["stages"][0]["counts"] == {"downloaded": 2}
        assert result["stages"][1]["errors"] == ["warn"]
        assert len(result["failures"]) == 1
        assert result["failures"][0]["item_id"] == "att-1"

    @patch("ccas.pipeline.worker.asyncio.run")
    @patch("ccas.storage.database.get_engine", new_callable=MagicMock)
    @patch("ccas.storage.database.get_session_factory", new_callable=MagicMock)
    @patch("ccas.pipeline.orchestrator.run_pipeline", new_callable=MagicMock)
    @patch("ccas.pipeline.options.PipelineOptions.from_dict")
    def test_none_opts_uses_default(
        self, mock_from_dict, mock_run, mock_sf, mock_engine, mock_asyncio_run
    ):
        summary = PipelineSummary(stages=(), total_seconds=0.1)
        mock_asyncio_run.return_value = summary
        mock_from_dict.return_value = MagicMock()

        result = run_pipeline_sync(None)

        mock_from_dict.assert_called_once_with(None)
        assert result["total_seconds"] == 0.1
        assert result["stages"] == []
        assert result["failures"] == []


class TestMarkManualReview:
    """驗證 mark_manual_review 的 SQL 更新邏輯。"""

    async def test_executes_update_and_commits(self):
        mock_result = MagicMock()
        mock_result.rowcount = 3
        session = AsyncMock()
        session.execute.return_value = mock_result

        count = await mark_manual_review(session)

        assert count == 3
        session.execute.assert_awaited_once()
        session.commit.assert_awaited_once()

    async def test_zero_affected_rows(self):
        mock_result = MagicMock()
        mock_result.rowcount = 0
        session = AsyncMock()
        session.execute.return_value = mock_result

        count = await mark_manual_review(session)

        assert count == 0


class TestOnFailureHandler:
    """驗證 on_failure_handler 的分支邏輯。"""

    @patch("ccas.pipeline.worker.asyncio.run")
    def test_marks_review_when_no_retries_left(self, mock_asyncio_run):
        mock_asyncio_run.return_value = 5
        job = MagicMock()
        job.id = "job-1"
        job.retries_left = 0

        on_failure_handler(job, MagicMock(), RuntimeError, RuntimeError("boom"), None)

        mock_asyncio_run.assert_called_once()

    @patch("ccas.pipeline.worker.asyncio.run")
    def test_marks_review_when_no_retries_attr(self, mock_asyncio_run):
        mock_asyncio_run.return_value = 2
        job = MagicMock(spec=[])  # no retries_left attribute
        job.id = "job-2"

        on_failure_handler(job, MagicMock(), RuntimeError, RuntimeError("boom"), None)

        mock_asyncio_run.assert_called_once()

    def test_skips_when_retries_remaining(self):
        job = MagicMock()
        job.retries_left = 2

        with patch("ccas.pipeline.worker.asyncio.run") as mock_run:
            on_failure_handler(
                job, MagicMock(), RuntimeError, RuntimeError("boom"), None
            )
            mock_run.assert_not_called()

    @patch("ccas.pipeline.worker.asyncio.run", side_effect=RuntimeError("db down"))
    def test_logs_error_on_mark_failure(self, mock_asyncio_run):
        job = MagicMock()
        job.id = "job-3"
        job.retries_left = 0

        # Should not raise; error is logged
        on_failure_handler(job, MagicMock(), RuntimeError, RuntimeError("boom"), None)

        mock_asyncio_run.assert_called_once()
