"""主動通知 rendering 與發送。

提供新帳單解析完成、到期提醒、解析失敗的訊息格式與發送流程。
排程觸發由 pipeline-scheduler 負責，此模組只負責內容格式與發送。
"""

import logging
from collections.abc import Sequence
from datetime import date

from ccas.bot.client import send_message
from ccas.storage.models import Bill

logger = logging.getLogger(__name__)


def render_new_bill_notification(
    bill: Bill,
    bank_name: str,
) -> str:
    """格式化新帳單解析完成通知。

    Args:
        bill: 已解析的帳單。
        bank_name: 銀行名稱。

    Returns:
        通知訊息文字。
    """
    return (
        f"新帳單已解析\n\n"
        f"銀行：{bank_name}\n"
        f"帳單月份：{bill.billing_month}\n"
        f"應繳金額：${bill.total_amount:,}\n"
        f"到期日：{bill.due_date}"
    )


def render_due_reminder(
    bill: Bill,
    bank_name: str,
    days_until_due: int,
) -> str:
    """格式化到期提醒訊息。

    Args:
        bill: 未繳帳單。
        bank_name: 銀行名稱。
        days_until_due: 距離到期的天數。

    Returns:
        提醒訊息文字。
    """
    urgency = "明天到期" if days_until_due <= 1 else f"{days_until_due} 天後到期"
    return (
        f"繳費提醒\n\n"
        f"銀行：{bank_name}\n"
        f"應繳金額：${bill.total_amount:,}\n"
        f"到期日：{bill.due_date}（{urgency}）\n\n"
        f"使用 /paid {bill.id} 標記已繳"
    )


def render_parse_failure_notification(
    bank_name: str,
    filename: str,
    error_reason: str | None,
) -> str:
    """格式化解析失敗通知。

    Args:
        bank_name: 銀行名稱。
        filename: 原始檔案名稱。
        error_reason: 失敗原因（可為 None）。

    Returns:
        異常通知訊息文字。
    """
    reason = error_reason or "未知錯誤"
    return (
        f"帳單解析失敗\n\n"
        f"銀行：{bank_name}\n"
        f"檔案：{filename}\n"
        f"原因：{reason}\n\n"
        f"請人工確認並重新處理。"
    )


async def notify_new_bill(
    bot_token: str,
    chat_id: str,
    bill: Bill,
    bank_name: str,
) -> None:
    """發送新帳單解析完成通知。"""
    text = render_new_bill_notification(bill, bank_name)
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
    logger.info(
        "Sent due reminder for bill #%d (%d days)", bill.id, days_until_due
    )


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
            await notify_due_reminder(
                bot_token, chat_id, bill, bank_name, days_left
            )
            sent_count += 1
        except Exception:
            logger.exception("Failed to send reminder for bill #%d", bill.id)

    return sent_count
