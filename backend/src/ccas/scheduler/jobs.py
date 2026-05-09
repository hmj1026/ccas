"""排程工作的同步封裝。

提供 APScheduler 與 RQ 可呼叫的同步函式。
"""

import asyncio
import logging

import httpx

from ccas.config import get_settings

logger = logging.getLogger(__name__)


def trigger_pipeline_via_api() -> None:
    """透過 API 端點觸發 pipeline（供 APScheduler 呼叫）。"""
    settings = get_settings()
    base_url = (
        settings.scheduler_api_base_url.rstrip("/")
        if settings.scheduler_api_base_url
        else f"http://127.0.0.1:{settings.api_port}"
    )
    url = f"{base_url}/api/pipeline/trigger"
    headers = {"Authorization": f"Bearer {settings.api_token}"}

    try:
        response = httpx.post(url, headers=headers, timeout=10)
        response.raise_for_status()
        logger.info("Pipeline triggered via API: %s", response.json())
    except Exception as exc:
        logger.error("Failed to trigger pipeline via API: %s", exc)
        raise


def run_payment_reminders_sync() -> dict[str, int]:
    """同步執行付款提醒（供 APScheduler 呼叫）。"""
    from ccas.scheduler.reminders import send_payment_reminders
    from ccas.storage.database import get_engine, get_session_factory

    async def _run() -> dict[str, int]:
        session_factory = get_session_factory()
        async with session_factory() as session:
            result = await send_payment_reminders(session)
        await get_engine().dispose()
        return result

    result = asyncio.run(_run())
    logger.info(
        "Payment reminders: sent=%d, skipped=%d", result["sent"], result["skipped"]
    )
    return result


def run_budget_evaluator_sync() -> dict[str, int]:
    """同步執行預算評估（供 APScheduler 呼叫）。"""
    from ccas.scheduler.budget_evaluator import evaluate_budgets
    from ccas.storage.database import get_engine, get_session_factory

    async def _run() -> dict[str, int]:
        session_factory = get_session_factory()
        async with session_factory() as session:
            result = await evaluate_budgets(session)
        await get_engine().dispose()
        return result

    result = asyncio.run(_run())
    logger.info(
        "Budget evaluator: alerts_triggered=%d, skipped=%d",
        result["alerts_triggered"],
        result["skipped"],
    )
    return result
