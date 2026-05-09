"""排程工作註冊測試。

5.4: 驗證 pipeline 工作與付款提醒工作均被正確註冊。
"""

from unittest.mock import MagicMock, patch

from ccas.scheduler.__main__ import main


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

        # 驗證 add_job 被呼叫了三次（pipeline / reminders / budget evaluator）
        assert mock_scheduler.add_job.call_count == 3

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
