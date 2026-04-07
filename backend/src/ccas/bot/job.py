"""批次通知 job 入口模組。

提供 run_notify_job() 作為 pipeline 的通知階段，
自動查詢未通知帳單並發送 Telegram 通知。
"""

import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.bot.client import send_message
from ccas.config import get_settings
from ccas.storage.models import Bill
from ccas.storage.queries import fetch_bank_names

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


async def run_notify_job(
    session: AsyncSession,
) -> NotifySummary:
    """查詢未通知帳單並發送 Telegram 通知。

    自動查詢 is_notified=False 的帳單，發送成功後標記為已通知。

    Args:
        session: 非同步 DB Session。

    Returns:
        NotifySummary 統計摘要。
    """
    summary = NotifySummary()

    settings = get_settings()
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        logger.info("TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID 未設定，跳過 notify stage")
        return summary

    stmt = select(Bill).where(Bill.is_notified.is_(False))
    result = await session.execute(stmt)
    bills = list(result.scalars().all())

    if not bills:
        logger.info("沒有未通知的帳單，跳過通知")
        return summary

    bank_names = await fetch_bank_names(session)

    # Pre-extract all scalar attributes before any session.commit/rollback to avoid
    # lazy-loading expired ORM objects (MissingGreenlet) on subsequent iterations.
    bill_rows = [
        (b.id, b.bank_code, b.billing_month, b.total_amount, b.due_date) for b in bills
    ]

    for bill_id, bill_code, bill_month, bill_total, bill_due in bill_rows:
        try:
            bank_name = bank_names.get(bill_code, bill_code)
            text = (
                f"新帳單已解析\n\n"
                f"銀行：{bank_name}\n"
                f"帳單月份：{bill_month}\n"
                f"應繳金額：${bill_total:,}\n"
                f"到期日：{bill_due}"
            )
            await send_message(
                settings.telegram_bot_token, settings.telegram_chat_id, text
            )
            # Use UPDATE query to mark notified (avoids touching expired ORM object)
            await session.execute(
                sa_update(Bill).where(Bill.id == bill_id).values(is_notified=True)
            )
            await session.commit()
            summary.sent_count += 1
            logger.info(
                "通知成功: bill #%d (%s/%s)",
                bill_id,
                bill_code,
                bill_month,
            )
        except Exception as exc:
            await session.rollback()
            error_msg = f"通知失敗 (bill #{bill_id}): {exc}"
            summary.failed_count += 1
            summary.errors.append(error_msg)
            logger.error(error_msg)

    return summary
