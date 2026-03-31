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
    url = f"http://{settings.api_host}:{settings.api_port}/api/pipeline/trigger"
    headers = {"Authorization": f"Bearer {settings.api_token}"}

    try:
        response = httpx.post(url, headers=headers, timeout=10)
        response.raise_for_status()
        logger.info("Pipeline triggered via API: %s", response.json())
    except Exception as exc:
        logger.error("Failed to trigger pipeline via API: %s", exc)


def run_payment_reminders_sync() -> dict[str, int]:
    """同步執行付款提醒（供 APScheduler 呼叫）。"""
    from ccas.scheduler.reminders import send_payment_reminders
    from ccas.storage.database import get_engine, get_session_factory

    async def _run() -> dict[str, int]:
        engine = get_engine()
        session_factory = get_session_factory(engine)
        async with session_factory() as session:
            result = await send_payment_reminders(session)
        await engine.dispose()
        return result

    result = asyncio.run(_run())
    logger.info("Payment reminders: sent=%d, skipped=%d", result["sent"], result["skipped"])
    return result
