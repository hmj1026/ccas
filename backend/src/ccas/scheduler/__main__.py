"""CLI 排程入口：python -m ccas.scheduler

啟動獨立的 APScheduler 行程，定期觸發 pipeline 與付款提醒。
與 FastAPI 和 RQ worker 分別運行。
"""

import logging
import signal
import sys

from apscheduler.schedulers.blocking import BlockingScheduler

from ccas.log import configure_logging
from ccas.scheduler.jobs import (
    run_budget_evaluator_sync,
    run_payment_reminders_sync,
    trigger_pipeline_via_api,
)

logger = logging.getLogger(__name__)


def main() -> None:
    configure_logging()
    """啟動 APScheduler 排程器。

    註冊的工作：
    - pipeline 觸發：每日午夜執行
    - 付款提醒：每日早上 9 點執行
    """
    scheduler = BlockingScheduler()

    # 每日午夜觸發 pipeline
    scheduler.add_job(
        trigger_pipeline_via_api,
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

    def _shutdown(signum, frame):
        logger.info("Received signal %d, shutting down scheduler", signum)
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    logger.info(
        "Starting scheduler with 3 jobs: daily_pipeline, "
        "daily_payment_reminders, daily_budget_evaluator"
    )
    scheduler.start()


if __name__ == "__main__":
    main()
