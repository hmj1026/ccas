"""trigger_pipeline_via_rq() 測試。

驗證 PipelineRun row 建立、RQ enqueue 參數與 API trigger 路徑語意一致。
"""

from unittest.mock import AsyncMock, MagicMock, patch

from rq import Retry

from ccas.pipeline.worker import on_failure_handler, run_pipeline_sync
from ccas.scheduler.jobs import trigger_pipeline_via_rq
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
