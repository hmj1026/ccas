"""主動通知發送流程。

提供新帳單解析完成、到期提醒、解析失敗的發送流程。
排程觸發由 pipeline-scheduler 負責，此模組只負責發送組合；
訊息格式（render_*）與 Telegram API 封裝（send_message）
已抽至共用模組 :mod:`ccas.messaging`。
"""

import logging
from datetime import date

from ccas.messaging import (
    render_due_reminder,
    render_new_bill_notification,
    render_parse_failure_notification,
    send_message,
)

logger = logging.getLogger(__name__)


async def notify_new_bill(
    bot_token: str,
    chat_id: str,
    *,
    bank_name: str,
    billing_month: str,
    total_amount: int,
    due_date: date | None,
    bill_id: int,
) -> None:
    """發送新帳單解析完成通知。

    接收純量參數（非 ``Bill`` ORM 物件），讓 ``session.commit()`` /
    ``rollback()`` 後 ORM 已 expire 的呼叫端（pipeline notify stage）也能安全
    共用，不觸發 lazy-load MissingGreenlet。
    """
    text = render_new_bill_notification(
        bank_name, billing_month, total_amount, due_date
    )
    await send_message(bot_token, chat_id, text)
    logger.info("Sent new bill notification for bill #%d", bill_id)


async def notify_due_reminder(
    bot_token: str,
    chat_id: str,
    *,
    bank_name: str,
    total_amount: int,
    due_date: date | None,
    bill_id: int,
    days_until_due: int,
    prefix: str = "",
) -> None:
    """發送到期提醒通知。

    接收純量參數（非 ``Bill`` ORM 物件）。``prefix`` 供測試推播端點在訊息前
    加上 ``[測試] `` 標記，預設為空字串（正式提醒不加前綴）。
    """
    text = prefix + render_due_reminder(
        bank_name, total_amount, due_date, bill_id, days_until_due
    )
    await send_message(bot_token, chat_id, text)
    logger.info("Sent due reminder for bill #%d (%d days)", bill_id, days_until_due)


async def notify_parse_failure(
    bot_token: str,
    chat_id: str,
    bank_name: str,
    filename: str,
    error_reason: str | None,
) -> None:
    """發送解析失敗通知。"""
    text = render_parse_failure_notification(bank_name, filename, error_reason)
    await send_message(bot_token, chat_id, text)
    logger.info("Sent parse failure notification for %s", filename)
