"""CLI 排程入口：python -m ccas.scheduler

啟動獨立的 APScheduler 行程，定期觸發 pipeline 與付款提醒。
與 FastAPI 和 RQ worker 分別運行。
"""

import logging
import signal
import sys
from functools import partial
from pathlib import Path

from apscheduler.events import EVENT_JOB_MISSED, JobExecutionEvent
from apscheduler.schedulers.blocking import BlockingScheduler

from ccas.config import get_settings
from ccas.log import configure_logging
from ccas.scheduler.jobs import (
    run_budget_evaluator_sync,
    run_payment_reminders_sync,
    trigger_pipeline_via_rq,
)

logger = logging.getLogger(__name__)


def _touch_heartbeat(path: Path) -> None:
    """Touch heartbeat file so docker compose healthcheck mtime probe stays green."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)


def _on_job_missed(event: JobExecutionEvent) -> None:
    """Log missed jobs (misfire beyond grace time) so operators can see them."""
    logger.warning(
        "Scheduler job missed: job_id=%s scheduled_run_time=%s",
        event.job_id,
        event.scheduled_run_time,
    )


def main() -> None:
    """啟動 APScheduler 排程器。

    註冊的工作：
    - pipeline 觸發：每日午夜執行
    - 付款提醒：每日早上 9 點執行
    """
    configure_logging()
    # misfire_grace_time: daily jobs may miss their slot when the host sleeps
    # or the container restarts; allow up to 1h late execution instead of
    # silently dropping the run. max_instances=1 prevents overlapping runs.
    scheduler = BlockingScheduler(
        job_defaults={"misfire_grace_time": 3600, "max_instances": 1}
    )

    # 每日午夜觸發 pipeline（直接 enqueue RQ，不經 API）
    scheduler.add_job(
        trigger_pipeline_via_rq,
        "cron",
        hour=0,
        minute=0,
        id="daily_pipeline",
        name="Daily pipeline trigger",
        replace_existing=True,
    )

    # 每日早上 9 點執行付款提醒
    scheduler.add_job(
        run_payment_reminders_sync,
        "cron",
        hour=9,
        minute=0,
        id="daily_payment_reminders",
        name="Daily payment reminders",
        replace_existing=True,
    )

    # 每日 02:00 執行預算評估（bills-management-and-insights §6.7）
    scheduler.add_job(
        run_budget_evaluator_sync,
        "cron",
        hour=2,
        minute=0,
        id="daily_budget_evaluator",
        name="Daily budget evaluator",
        replace_existing=True,
    )

    # heartbeat：每 30 秒 touch 檔，docker compose §1.11 worker/scheduler healthcheck
    # 透過 mtime 判斷 scheduler 是否仍存活；先 touch 一次避免 healthcheck 在
    # start_period 結束前 mtime 不存在。eager touch 失敗 (read-only fs / 權限不足)
    # 不應 crash scheduler — 30s interval job 由 APScheduler executor 包，會
    # 自動 log 後續失敗；operator 看到 warning 才知道要修檔案系統權限。
    heartbeat_path = get_settings().scheduler_heartbeat_path
    try:
        _touch_heartbeat(heartbeat_path)
    except OSError as exc:
        logger.warning(
            "scheduler heartbeat initial touch failed at %s: %s — "
            "directory may be read-only or permission-denied; "
            "30s interval job will retry",
            heartbeat_path,
            exc,
        )
    scheduler.add_job(
        partial(_touch_heartbeat, heartbeat_path),
        "interval",
        seconds=30,
        id="scheduler_heartbeat",
        name="Scheduler heartbeat writer",
        replace_existing=True,
        # A late heartbeat touch is useless (next tick is 30s away); override
        # the 1h default so missed ticks are dropped (and logged) instead.
        misfire_grace_time=15,
    )

    def _shutdown(signum, frame):
        logger.info("Received signal %d, shutting down scheduler", signum)
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    # Surface dropped runs (misfire beyond grace time) in logs at warning level.
    scheduler.add_listener(_on_job_missed, EVENT_JOB_MISSED)

    logger.info(
        "Starting scheduler with 4 jobs: daily_pipeline, "
        "daily_payment_reminders, daily_budget_evaluator, scheduler_heartbeat"
    )
    scheduler.start()


if __name__ == "__main__":
    main()
