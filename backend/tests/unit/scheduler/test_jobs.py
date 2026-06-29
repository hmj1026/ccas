"""trigger_pipeline_via_rq() 測試。

驗證 PipelineRun row 建立、RQ enqueue 參數與 API trigger 路徑語意一致。
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from rq import Retry

from ccas.pipeline.worker import on_failure_handler, run_pipeline_sync
from ccas.scheduler.jobs import (
    run_budget_evaluator_sync,
    run_payment_reminders_sync,
    trigger_pipeline_via_rq,
)
from ccas.storage.models import PipelineRun, PipelineRunStatus


def _make_db_mocks(run_obj: object | None = None):
    """建立 async session factory / engine mocks。"""
    session = MagicMock()
    session.commit = AsyncMock()
    session.get = AsyncMock(return_value=run_obj)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    factory = MagicMock(return_value=ctx)
    engine = MagicMock()
    engine.dispose = AsyncMock()
    return factory, engine, session


def _run_with_mocks(opts: dict | None = None, run_obj: object | None = None):
    """以完整 mock 環境執行 trigger_pipeline_via_rq，回傳觀測點。"""
    factory, engine, session = _make_db_mocks(run_obj)
    queue = MagicMock()
    queue.enqueue.return_value = MagicMock(id="rq-job-123")
    settings = MagicMock()
    settings.redis_url = "redis://test:6379/0"

    with (
        patch("ccas.scheduler.jobs.get_settings", return_value=settings),
        patch("ccas.scheduler.jobs.Redis") as mock_redis,
        patch("ccas.scheduler.jobs.Queue", return_value=queue) as mock_queue_cls,
        patch("ccas.storage.database.get_session_factory", return_value=factory),
        patch("ccas.storage.database.get_engine", return_value=engine),
    ):
        result = trigger_pipeline_via_rq(opts)

    return {
        "result": result,
        "session": session,
        "engine": engine,
        "queue": queue,
        "mock_redis": mock_redis,
        "mock_queue_cls": mock_queue_cls,
    }


class TestPipelineRunCreation:
    """PipelineRun row 建立語意（與 API trigger 端點一致）。"""

    def test_creates_queued_run_with_scheduler_trigger(self):
        """row 應為 QUEUED、triggered_by=scheduler、stage_summary=[]。"""
        env = _run_with_mocks()

        env["session"].add.assert_called_once()
        run = env["session"].add.call_args[0][0]
        assert isinstance(run, PipelineRun)
        assert run.status == PipelineRunStatus.QUEUED
        assert run.triggered_by == "scheduler"
        assert run.params == {}
        assert run.stage_summary == []
        # id/job_id pattern: initially both equal run_id
        assert run.id == run.job_id

    def test_params_default_to_empty_dict_when_opts_none(self):
        """opts=None 時 params 應為 {}（非 None）。"""
        env = _run_with_mocks(opts=None)
        run = env["session"].add.call_args[0][0]
        assert run.params == {}

    def test_params_pass_through(self):
        """opts dict 應原樣寫入 params。"""
        opts = {"force": True, "bank_code": "CTBC"}
        env = _run_with_mocks(opts=opts)
        run = env["session"].add.call_args[0][0]
        assert run.params == opts

    def test_job_id_updated_after_enqueue(self):
        """enqueue 後應把 RQ job.id 寫回 PipelineRun.job_id。"""
        run_obj = MagicMock()
        env = _run_with_mocks(run_obj=run_obj)

        assert run_obj.job_id == "rq-job-123"
        # two commits: row creation + job_id update
        assert env["session"].commit.await_count == 2

    def test_engine_disposed_after_run(self):
        """asyncio.run 結束前應 dispose engine（避免殘留連線）。"""
        env = _run_with_mocks()
        env["engine"].dispose.assert_awaited_once()


class TestRqEnqueueSemantics:
    """RQ enqueue 參數須與 API trigger 路徑完全一致。"""

    def test_enqueue_args_match_api_path(self):
        """opts 為第一個位置參數（on_failure_handler 讀 job.args[0]）。"""
        opts = {"force": False, "bank_code": "ESUN"}
        env = _run_with_mocks(opts=opts)

        env["queue"].enqueue.assert_called_once()
        call = env["queue"].enqueue.call_args
        assert call.args[0] is run_pipeline_sync
        assert call.args[1] == opts
        assert call.kwargs["on_failure"] is on_failure_handler
        assert call.kwargs["job_timeout"] == "30m"
        assert isinstance(call.kwargs["retry"], Retry)

        run = env["session"].add.call_args[0][0]
        assert call.kwargs["run_id"] == run.id

    def test_returns_rq_job_id(self):
        """回傳值應為 RQ job id。"""
        env = _run_with_mocks()
        assert env["result"] == "rq-job-123"

    def test_uses_redis_url_from_settings(self):
        """Redis 連線應使用 settings.redis_url。"""
        env = _run_with_mocks()
        env["mock_redis"].from_url.assert_called_once_with("redis://test:6379/0")
        env["mock_queue_cls"].assert_called_once_with(
            connection=env["mock_redis"].from_url.return_value
        )


def _run_with_enqueue_failure(run_obj: object | None):
    """以 enqueue 失敗的環境執行 trigger_pipeline_via_rq，回傳觀測點。"""
    factory, engine, session = _make_db_mocks(run_obj)
    queue = MagicMock()
    queue.enqueue.side_effect = RuntimeError("redis down")
    settings = MagicMock()
    settings.redis_url = "redis://test:6379/0"

    with (
        patch("ccas.scheduler.jobs.get_settings", return_value=settings),
        patch("ccas.scheduler.jobs.Redis"),
        patch("ccas.scheduler.jobs.Queue", return_value=queue),
        patch("ccas.storage.database.get_session_factory", return_value=factory),
        patch("ccas.storage.database.get_engine", return_value=engine),
    ):
        with pytest.raises(RuntimeError, match="redis down"):
            trigger_pipeline_via_rq()

    return {"session": session, "engine": engine}


class TestEnqueueFailurePath:
    """enqueue 失敗：孤兒 QUEUED row 應標記 FAILED 並 re-raise（鏡像 API path）。"""

    def test_marks_orphan_run_failed_and_reraises(self):
        """run 存在時應寫 FAILED + error_message，並 commit 兩次後 re-raise。"""
        run_obj = MagicMock()
        env = _run_with_enqueue_failure(run_obj)

        assert run_obj.status == PipelineRunStatus.FAILED
        assert run_obj.error_message == "Pipeline enqueue failed (scheduler)"
        # 1st commit = QUEUED row 建立, 2nd commit = FAILED 標記
        assert env["session"].commit.await_count == 2

    def test_engine_not_disposed_when_enqueue_fails(self):
        """enqueue 在 dispose 之前丟出，故 engine.dispose 不應被 await。"""
        env = _run_with_enqueue_failure(MagicMock())
        env["engine"].dispose.assert_not_awaited()

    def test_missing_run_row_still_reraises(self):
        """run 取不到（None）時不標記，但仍 re-raise；只 commit 一次。"""
        env = _run_with_enqueue_failure(run_obj=None)
        assert env["session"].commit.await_count == 1


def _run_reminders(result=None, side_effect=None):
    """以完整 mock 環境執行 run_payment_reminders_sync，回傳觀測點。"""
    factory, engine, session = _make_db_mocks()
    reminders = AsyncMock(return_value=result, side_effect=side_effect)
    with (
        patch("ccas.scheduler.reminders.send_payment_reminders", reminders),
        patch("ccas.storage.database.get_session_factory", return_value=factory),
        patch("ccas.storage.database.get_engine", return_value=engine),
    ):
        if side_effect is not None:
            with pytest.raises(type(side_effect)):
                run_payment_reminders_sync()
            return {"engine": engine, "session": session, "reminders": reminders}
        out = run_payment_reminders_sync()
        return {
            "result": out,
            "engine": engine,
            "session": session,
            "reminders": reminders,
        }


class TestRunPaymentRemindersSync:
    """同步封裝：開 session → 呼叫 send_payment_reminders → dispose engine。"""

    def test_returns_result_and_disposes_engine(self):
        env = _run_reminders(result={"sent": 2, "skipped": 1})
        assert env["result"] == {"sent": 2, "skipped": 1}
        env["reminders"].assert_awaited_once_with(env["session"])
        env["engine"].dispose.assert_awaited_once()

    def test_reraises_on_failure(self):
        env = _run_reminders(side_effect=RuntimeError("reminder boom"))
        # 失敗發生在 dispose 之前 → engine 未被 dispose
        env["engine"].dispose.assert_not_awaited()


def _run_budget(result=None, side_effect=None):
    """以完整 mock 環境執行 run_budget_evaluator_sync，回傳觀測點。"""
    factory, engine, session = _make_db_mocks()
    evaluator = AsyncMock(return_value=result, side_effect=side_effect)
    with (
        patch("ccas.scheduler.budget_evaluator.evaluate_budgets", evaluator),
        patch("ccas.storage.database.get_session_factory", return_value=factory),
        patch("ccas.storage.database.get_engine", return_value=engine),
    ):
        if side_effect is not None:
            with pytest.raises(type(side_effect)):
                run_budget_evaluator_sync()
            return {"engine": engine, "session": session, "evaluator": evaluator}
        out = run_budget_evaluator_sync()
        return {
            "result": out,
            "engine": engine,
            "session": session,
            "evaluator": evaluator,
        }


class TestRunBudgetEvaluatorSync:
    """同步封裝：開 session → 呼叫 evaluate_budgets → dispose engine。"""

    def test_returns_result_and_disposes_engine(self):
        env = _run_budget(result={"alerts_triggered": 3, "skipped": 4})
        assert env["result"] == {"alerts_triggered": 3, "skipped": 4}
        env["evaluator"].assert_awaited_once_with(env["session"])
        env["engine"].dispose.assert_awaited_once()

    def test_reraises_on_failure(self):
        env = _run_budget(side_effect=RuntimeError("budget boom"))
        env["engine"].dispose.assert_not_awaited()
