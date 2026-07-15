"""``ccas.pipeline.lifecycle`` 的單元測試。

涵蓋 ``RunLifecycle`` 的失敗分類判定（自 ``test_worker.py`` 移入）、
``stage_progress`` 換算，以及 ``InMemoryLifecycleStore`` 的 persist_* 行為。
"""

from __future__ import annotations

from ccas.pipeline.lifecycle import (
    InMemoryLifecycleStore,
    LifecycleResult,
    RunLifecycle,
    StageProgress,
)
from ccas.pipeline.summary import PipelineSummary, StageSummary
from ccas.storage.models import PipelineRunStatus


class TestStageProgress:
    """驗證 RunLifecycle.stage_progress 的 (ok, fail) 換算。"""

    def test_ok_and_fail_split(self):
        summary = StageSummary(
            stage="ingest", counts={"staged": 3, "skipped": 1, "failed": 2}
        )
        ok, fail = RunLifecycle.stage_progress(summary)
        assert ok == 4
        assert fail == 2

    def test_no_failed_key_defaults_zero(self):
        summary = StageSummary(stage="classify", counts={"classified": 5})
        ok, fail = RunLifecycle.stage_progress(summary)
        assert ok == 5
        assert fail == 0


class TestFailureClassification:
    """驗證 RunLifecycle._classify_batch_failed 與 failure_reason 的判定。"""

    def test_classify_batch_failed_true(self):
        summary = PipelineSummary(
            stages=(StageSummary(stage="classify", counts={"failed": 2}),),
            total_seconds=1.0,
        )
        assert RunLifecycle._classify_batch_failed(summary) is True

    def test_classify_batch_failed_false_on_success_counts(self):
        summary = PipelineSummary(
            stages=(StageSummary(stage="classify", counts={"classified": 5}),),
            total_seconds=1.0,
        )
        assert RunLifecycle._classify_batch_failed(summary) is False

    def test_run_failure_reason_classify(self):
        summary = PipelineSummary(
            stages=(StageSummary(stage="classify", counts={"failed": 1}),),
            total_seconds=1.0,
        )
        reason = RunLifecycle.failure_reason(summary)
        assert reason is not None
        assert "classify" in reason

    def test_run_failure_reason_stage_error(self):
        summary = PipelineSummary(
            stages=(StageSummary(stage="ingest", counts={}, errors=["page 2 failed"]),),
            total_seconds=1.0,
        )
        reason = RunLifecycle.failure_reason(summary)
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
        assert RunLifecycle.failure_reason(summary) is None

    def test_run_failure_reason_success(self):
        summary = PipelineSummary(
            stages=(StageSummary(stage="parse", counts={"parsed": 3}),),
            total_seconds=1.0,
        )
        assert RunLifecycle.failure_reason(summary) is None


class TestClassify:
    """驗證 RunLifecycle.classify 回傳的 LifecycleResult。"""

    def test_classify_batch_failed_yields_failed_result(self):
        summary = PipelineSummary(
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
        result = RunLifecycle.classify(summary)
        assert result.status == PipelineRunStatus.FAILED
        assert result.error_message is not None
        assert "classify" in result.error_message
        assert result.stage_progress == (
            StageProgress(stage="ingest", ok=2, fail=0),
            StageProgress(stage="classify", ok=0, fail=1),
        )

    def test_notify_only_failure_yields_succeeded_result(self):
        summary = PipelineSummary(
            stages=(
                StageSummary(stage="parse", counts={"parsed": 2}),
                StageSummary(
                    stage="notify",
                    counts={"sent": 1, "failed": 1},
                    errors=["telegram timeout"],
                ),
            ),
            total_seconds=0.2,
        )
        result = RunLifecycle.classify(summary)
        assert result.status == PipelineRunStatus.SUCCEEDED
        assert result.error_message is None

    def test_success_summary_yields_succeeded_result(self):
        summary = PipelineSummary(
            stages=(StageSummary(stage="ingest", counts={"staged": 3}),),
            total_seconds=0.5,
        )
        result = RunLifecycle.classify(summary)
        assert result.status == PipelineRunStatus.SUCCEEDED
        assert result.error_message is None


class TestLifecycleResultFailed:
    def test_failed_classmethod_builds_failed_result(self):
        result = LifecycleResult.failed("RuntimeError: boom")
        assert result.status == PipelineRunStatus.FAILED
        assert result.error_message == "RuntimeError: boom"
        assert result.stage_progress == ()


class TestInMemoryLifecycleStore:
    """驗證 InMemoryLifecycleStore 記錄 persist_progress / persist_terminal 的行為。"""

    async def test_persist_progress_records_run_id(self):
        store = InMemoryLifecycleStore()
        await store.persist_progress("run-1")
        assert store.progress_started == ["run-1"]

    async def test_persist_terminal_records_failed_outcome(self):
        store = InMemoryLifecycleStore()
        summary = PipelineSummary(
            stages=(
                StageSummary(
                    stage="parse",
                    counts={"failed": 1},
                    errors=["ParseError: 無法解析 PDF"],
                ),
            ),
            total_seconds=0.3,
        )
        result = RunLifecycle.classify(summary)
        await store.persist_terminal("run-2", result)

        assert store.terminals["run-2"].status == PipelineRunStatus.FAILED
        assert store.terminals["run-2"].error_message is not None

    async def test_persist_terminal_records_succeeded_outcome(self):
        store = InMemoryLifecycleStore()
        summary = PipelineSummary(
            stages=(
                StageSummary(stage="parse", counts={"parsed": 2}),
                StageSummary(
                    stage="notify",
                    counts={"sent": 0, "failed": 1},
                    errors=["telegram timeout"],
                ),
            ),
            total_seconds=0.4,
        )
        result = RunLifecycle.classify(summary)
        await store.persist_terminal("run-3", result)

        assert store.terminals["run-3"].status == PipelineRunStatus.SUCCEEDED
        assert store.terminals["run-3"].error_message is None
