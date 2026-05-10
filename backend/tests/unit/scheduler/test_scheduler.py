"""排程工作註冊測試。

5.4: 驗證 pipeline 工作與付款提醒工作均被正確註冊。
"""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from ccas.scheduler.__main__ import _touch_heartbeat, main


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
