"""批次通知 job 入口模組。

提供 run_notify_job() 作為 pipeline 的通知階段，
對新解析的帳單發送 Telegram 通知。
"""

import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.bot.client import send_message
from ccas.bot.notifications import render_new_bill_notification
from ccas.config import get_settings
from ccas.storage.models import BankConfig, Bill

logger = logging.getLogger(__name__)


@dataclass
class NotifySummary:
    """通知階段的統計摘要。

    Attributes:
        sent_count: 成功發送的通知數。
        failed_count: 發送失敗的數量。
        errors: 錯誤訊息清單。
    """

    sent_count: int = 0
    failed_count: int = 0
    errors: list[str] = field(default_factory=list)


async def _fetch_bank_names(session: AsyncSession) -> dict[str, str]:
    """查詢銀行代碼到名稱的對照表。"""
    stmt = select(BankConfig.bank_code, BankConfig.bank_name)
    result = await session.execute(stmt)
    return {row[0]: row[1] for row in result.all()}


async def run_notify_job(
    session: AsyncSession,
    *,
    bill_ids: list[int] | None = None,
) -> NotifySummary:
    """對指定帳單發送 Telegram 新帳單通知。

    Args:
        session: 非同步 DB Session。
        bill_ids: 要通知的帳單 ID 清單。若為 None 或空則略過。

    Returns:
        NotifySummary 統計摘要。
    """
    summary = NotifySummary()

    if not bill_ids:
        return summary

    settings = get_settings()
    bank_names = await _fetch_bank_names(session)

    stmt = select(Bill).where(Bill.id.in_(bill_ids))
    result = await session.execute(stmt)
    bills = list(result.scalars().all())

    for bill in bills:
        try:
            bank_name = bank_names.get(bill.bank_code, bill.bank_code)
            text = render_new_bill_notification(bill, bank_name)
            await send_message(
                settings.telegram_bot_token, settings.telegram_chat_id, text
            )
            summary.sent_count += 1
        except Exception as exc:
            error_msg = f"通知失敗 (bill #{bill.id}): {exc}"
            summary.failed_count += 1
            summary.errors.append(error_msg)
            logger.error(error_msg)

    return summary
