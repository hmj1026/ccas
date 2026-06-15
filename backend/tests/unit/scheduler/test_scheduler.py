"""排程工作註冊測試。

5.4: 驗證 pipeline 工作與付款提醒工作均被正確註冊。
"""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_MISSED

from ccas.scheduler.__main__ import (
    _on_job_error,
    _on_job_missed,
    _touch_heartbeat,
    main,
)
from ccas.scheduler.jobs import trigger_pipeline_via_rq


def _run_main_with_mock_scheduler() -> MagicMock:
    """以 mock BlockingScheduler 執行 main()，回傳 scheduler class mock。"""
    mock_scheduler = MagicMock()
    mock_scheduler.start.side_effect = KeyboardInterrupt

    with (
        patch(
            "ccas.scheduler.__main__.BlockingScheduler", return_value=mock_scheduler
        ) as mock_cls,
        patch("ccas.scheduler.__main__.signal.signal"),
    ):
        try:
            main()
        except (KeyboardInterrupt, SystemExit):
            pass

    mock_cls.scheduler_instance = mock_scheduler
    return mock_cls


class TestSchedulerJobRegistration:
    """5.4: 驗證 scheduler 註冊了 pipeline 觸發與付款提醒兩個工作。"""

    def test_scheduler_registers_both_jobs(self):
        """scheduler.main() 應註冊兩個預設工作。"""
        mock_scheduler = MagicMock()
        # start() 會 block，所以讓它拋出 KeyboardInterrupt 來結束
        mock_scheduler.start.side_effect = KeyboardInterrupt

        with (
            patch(
                "ccas.scheduler.__main__.BlockingScheduler", return_value=mock_scheduler
            ),
            patch("ccas.scheduler.__main__.signal.signal"),
        ):
            try:
                main()
            except (KeyboardInterrupt, SystemExit):
                pass

        # add_job called four times: pipeline / reminders / budget evaluator / heartbeat
        assert mock_scheduler.add_job.call_count == 4

        # 收集註冊的 job IDs
        job_ids = set()
        for call in mock_scheduler.add_job.call_args_list:
            job_ids.add(call.kwargs.get("id") or call[1].get("id"))

        assert "daily_pipeline" in job_ids
        assert "daily_payment_reminders" in job_ids
        assert "daily_budget_evaluator" in job_ids

    def test_pipeline_job_uses_cron_trigger(self):
        """pipeline 工作使用 cron trigger，每日午夜。"""
        mock_scheduler = MagicMock()
        mock_scheduler.start.side_effect = KeyboardInterrupt

        with (
            patch(
                "ccas.scheduler.__main__.BlockingScheduler", return_value=mock_scheduler
            ),
            patch("ccas.scheduler.__main__.signal.signal"),
        ):
            try:
                main()
            except (KeyboardInterrupt, SystemExit):
                pass

        pipeline_call = None
        for call in mock_scheduler.add_job.call_args_list:
            if call.kwargs.get("id") == "daily_pipeline":
                pipeline_call = call
                break

        assert pipeline_call is not None
        # 第二個位置參數是 trigger type
        assert pipeline_call.args[1] == "cron"
        assert pipeline_call.kwargs["hour"] == 0
        assert pipeline_call.kwargs["minute"] == 0

    def test_reminders_job_runs_at_9am(self):
        """付款提醒工作在每日早上 9 點執行。"""
        mock_scheduler = MagicMock()
        mock_scheduler.start.side_effect = KeyboardInterrupt

        with (
            patch(
                "ccas.scheduler.__main__.BlockingScheduler", return_value=mock_scheduler
            ),
            patch("ccas.scheduler.__main__.signal.signal"),
        ):
            try:
                main()
            except (KeyboardInterrupt, SystemExit):
                pass

        reminders_call = None
        for call in mock_scheduler.add_job.call_args_list:
            if call.kwargs.get("id") == "daily_payment_reminders":
                reminders_call = call
                break

        assert reminders_call is not None
        assert reminders_call.kwargs["hour"] == 9
        assert reminders_call.kwargs["minute"] == 0

    def test_heartbeat_job_registered(self, tmp_path: Path):
        """heartbeat job 以 30s interval 註冊，docker compose §1.11 healthcheck 依賴
        scheduler 持續寫入 ${CCAS_DATA_LOCATION}/scheduler-heartbeat 來確認存活。
        """
        mock_scheduler = MagicMock()
        mock_scheduler.start.side_effect = KeyboardInterrupt

        with (
            patch(
                "ccas.scheduler.__main__.BlockingScheduler", return_value=mock_scheduler
            ),
            patch("ccas.scheduler.__main__.signal.signal"),
        ):
            try:
                main()
            except (KeyboardInterrupt, SystemExit):
                pass

        heartbeat_call = None
        for call in mock_scheduler.add_job.call_args_list:
            if call.kwargs.get("id") == "scheduler_heartbeat":
                heartbeat_call = call
                break

        assert heartbeat_call is not None
        assert heartbeat_call.args[1] == "interval"
        assert heartbeat_call.kwargs["seconds"] == 30

    def test_touch_heartbeat_creates_and_updates(self, tmp_path: Path):
        """_touch_heartbeat 首次建立檔案、二次更新 mtime；目錄不存在時自動 mkdir。"""
        target = tmp_path / "nested" / "scheduler-heartbeat"

        _touch_heartbeat(target)
        assert target.is_file()
        first_mtime = target.stat().st_mtime

        # 強制改 mtime 模擬時間流逝
        os.utime(target, (first_mtime - 60, first_mtime - 60))

        _touch_heartbeat(target)
        assert target.stat().st_mtime > first_mtime - 60

    def test_main_logs_warning_when_initial_heartbeat_touch_fails(self, caplog):
        """Issue #9: read-only fs / permission-denied 時不應讓 scheduler 直接
        crash。Eager touch 失敗時記 warning，讓 30s interval job 後續重試；
        operator 看到 log 才知道要修檔案系統權限。
        """
        import logging

        mock_scheduler = MagicMock()
        mock_scheduler.start.side_effect = KeyboardInterrupt

        with (
            patch(
                "ccas.scheduler.__main__.BlockingScheduler", return_value=mock_scheduler
            ),
            patch("ccas.scheduler.__main__.signal.signal"),
            # configure_logging() resets handlers, dropping pytest's caplog
            # listener. Stub it so caplog can observe the warning record.
            patch("ccas.scheduler.__main__.configure_logging"),
            # Single-shot side_effect: only the eager touch fails. The interval
            # job's ``partial(_touch_heartbeat, ...)`` (registered after) would
            # wrap the real function in production; the mocked ``add_job`` here
            # never invokes the partial so this is mostly cosmetic — but it
            # keeps the patch scoped to what the test actually asserts.
            patch(
                "ccas.scheduler.__main__._touch_heartbeat",
                side_effect=[PermissionError(13, "Permission denied")],
            ),
            caplog.at_level(logging.WARNING, logger="ccas.scheduler.__main__"),
        ):
            try:
                main()
            except (KeyboardInterrupt, SystemExit):
                pass

        # Scheduler must still start (interval job will retry the touch every 30s)
        mock_scheduler.start.assert_called_once()

        # Warning must be logged so the operator sees the cause
        warnings = [
            rec
            for rec in caplog.records
            if rec.levelno == logging.WARNING and "heartbeat" in rec.getMessage()
        ]
        assert warnings, (
            "expected at least one heartbeat-related warning log when "
            "_touch_heartbeat raises OSError"
        )

    def test_budget_evaluator_runs_at_2am(self):
        """預算評估在每日凌晨 2 點執行（§6.7）。"""
        mock_scheduler = MagicMock()
        mock_scheduler.start.side_effect = KeyboardInterrupt

        with (
            patch(
                "ccas.scheduler.__main__.BlockingScheduler", return_value=mock_scheduler
            ),
            patch("ccas.scheduler.__main__.signal.signal"),
        ):
            try:
                main()
            except (KeyboardInterrupt, SystemExit):
                pass

        evaluator_call = None
        for call in mock_scheduler.add_job.call_args_list:
            if call.kwargs.get("id") == "daily_budget_evaluator":
                evaluator_call = call
                break

        assert evaluator_call is not None
        assert evaluator_call.args[1] == "cron"
        assert evaluator_call.kwargs["hour"] == 2
        assert evaluator_call.kwargs["minute"] == 0

    def test_pipeline_job_targets_rq_trigger(self):
        """pipeline 工作直接 enqueue RQ（不再經 HTTP API）。"""
        mock_cls = _run_main_with_mock_scheduler()
        scheduler = mock_cls.scheduler_instance

        pipeline_call = None
        for call in scheduler.add_job.call_args_list:
            if call.kwargs.get("id") == "daily_pipeline":
                pipeline_call = call
                break

        assert pipeline_call is not None
        assert pipeline_call.args[0] is trigger_pipeline_via_rq


class TestSchedulerMisfirePolicy:
    """misfire 防護：job_defaults、heartbeat 覆寫與 missed listener。"""

    def test_scheduler_job_defaults(self):
        """BlockingScheduler 應設定 misfire_grace_time=3600、max_instances=1。"""
        mock_cls = _run_main_with_mock_scheduler()

        mock_cls.assert_called_once()
        job_defaults = mock_cls.call_args.kwargs["job_defaults"]
        assert job_defaults["misfire_grace_time"] == 3600
        assert job_defaults["max_instances"] == 1

    def test_heartbeat_overrides_misfire_grace_time(self):
        """heartbeat job 的 misfire_grace_time 應短於全域 1h 預設。"""
        mock_cls = _run_main_with_mock_scheduler()
        scheduler = mock_cls.scheduler_instance

        heartbeat_call = None
        for call in scheduler.add_job.call_args_list:
            if call.kwargs.get("id") == "scheduler_heartbeat":
                heartbeat_call = call
                break

        assert heartbeat_call is not None
        assert heartbeat_call.kwargs["misfire_grace_time"] < 3600

    def test_missed_job_listener_registered_before_start(self):
        """main() 應在 start() 前註冊 EVENT_JOB_MISSED + EVENT_JOB_ERROR listener。"""
        mock_cls = _run_main_with_mock_scheduler()
        scheduler = mock_cls.scheduler_instance

        # Both the missed-job and the job-error listeners must be registered.
        listener_calls = [
            (call.args[0], call.args[1])
            for call in scheduler.add_listener.call_args_list
        ]
        assert (_on_job_missed, EVENT_JOB_MISSED) in listener_calls
        assert (_on_job_error, EVENT_JOB_ERROR) in listener_calls
        # registered before the (blocking) start() call
        method_order = [name for name, *_ in scheduler.mock_calls]
        assert method_order.index("add_listener") < method_order.index("start")

    def test_on_job_missed_logs_warning(self, caplog):
        """_on_job_missed 應以 warning 記錄 job_id 與 scheduled_run_time。"""
        import logging

        event = MagicMock()
        event.job_id = "daily_pipeline"
        event.scheduled_run_time = "2026-06-11 00:00:00+00:00"

        with caplog.at_level(logging.WARNING, logger="ccas.scheduler.__main__"):
            _on_job_missed(event)

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert warnings
        message = warnings[0].getMessage()
        assert "daily_pipeline" in message
        assert "2026-06-11 00:00:00+00:00" in message
