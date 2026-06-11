"""主動通知發送流程。

提供新帳單解析完成、到期提醒、解析失敗的發送流程。
排程觸發由 pipeline-scheduler 負責，此模組只負責發送組合；
訊息格式（render_*）與 Telegram API 封裝（send_message）
已抽至共用模組 :mod:`ccas.messaging`。
"""

import logging
from collections.abc import Sequence
from datetime import date

from ccas.messaging import (
    render_due_reminder,
    render_new_bill_notification,
    render_parse_failure_notification,
    send_message,
)
from ccas.storage.models import Bill

logger = logging.getLogger(__name__)


async def notify_new_bill(
    bot_token: str,
    chat_id: str,
    bill: Bill,
    bank_name: str,
) -> None:
    """發送新帳單解析完成通知。"""
    text = render_new_bill_notification(
        bank_name, bill.billing_month, bill.total_amount, bill.due_date
    )
    await send_message(bot_token, chat_id, text)
    logger.info("Sent new bill notification for bill #%d", bill.id)


async def notify_due_reminder(
    bot_token: str,
    chat_id: str,
    bill: Bill,
    bank_name: str,
    days_until_due: int,
) -> None:
    """發送到期提醒通知。"""
    text = render_due_reminder(bill, bank_name, days_until_due)
    await send_message(bot_token, chat_id, text)
    logger.info("Sent due reminder for bill #%d (%d days)", bill.id, days_until_due)


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


async def send_due_reminders(
    bot_token: str,
    chat_id: str,
    bills: Sequence[Bill],
    bank_names: dict[str, str],
    *,
    today: date | None = None,
) -> int:
    """批次發送到期提醒。

    Args:
        bot_token: Bot API 權杖。
        chat_id: 目標聊天室。
        bills: 需要提醒的帳單清單。
        bank_names: bank_code → bank_name 對照。
        today: 基準日。

    Returns:
        成功發送的通知數量。
    """
    if today is None:
        today = date.today()

    sent_count = 0
    for bill in bills:
        days_left = (bill.due_date - today).days
        bank_name = bank_names.get(bill.bank_code, bill.bank_code)
        try:
            await notify_due_reminder(bot_token, chat_id, bill, bank_name, days_left)
            sent_count += 1
        except Exception:
            logger.exception("Failed to send reminder for bill #%d", bill.id)

    return sent_count
