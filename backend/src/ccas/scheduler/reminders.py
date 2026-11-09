"""付款提醒排程工作。

查詢未付帳單並透過 Telegram 發送到期前 3 天與 1 天的提醒。
以 (bill_id, reminder_type) 唯一鍵防止重複發送（通知投遞規則見 ccas.outbox）。
"""

import logging
from datetime import date, timedelta
from functools import partial

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.config import get_settings
from ccas.messaging import render_due_reminder
from ccas.outbox import DeliveryStatus, Outbox, PaymentReminderClaim
from ccas.storage.models import Bill
from ccas.storage.queries import fetch_bank_names

logger = logging.getLogger(__name__)

# 估算到期日（CTBC 兩頁帳單 day-28 fallback）放寬比對窗（天）。
# 估算值可能高估真實截止日（月底/假日順延），太晚提醒會誤事；故對
# ``due_date_estimated`` 帳單以 [target_date, target_date + N] 區間比對，
# 讓高估的日期仍能提早觸發及時提醒。idempotency 仍以 (bill_id,
# reminder_type) 唯一鍵把關，放寬窗不會重複發送。
_ESTIMATED_DUE_WIDEN_DAYS = 3


async def _fetch_unpaid_bills_due_on(
    session: AsyncSession,
    target_date: date,
) -> list[Bill]:
    """查詢應於指定日期提醒且未付的帳單。

    精確到期日帳單以 ``due_date == target_date`` 比對；``due_date_estimated``
    為 True 的帳單（到期日為估算值）改以 ``target_date <= due_date <=
    target_date + _ESTIMATED_DUE_WIDEN_DAYS`` 區間比對，避免高估的截止日造成
    提醒過晚。重複發送由 (bill_id, reminder_type) 唯一鍵防範（claim 機制）。
    """
    widened_end = target_date + timedelta(days=_ESTIMATED_DUE_WIDEN_DAYS)
    stmt = (
        select(Bill)
        .where(
            Bill.is_paid.is_(False),
            or_(
                Bill.due_date == target_date,
                and_(
                    Bill.due_date_estimated.is_(True),
                    Bill.due_date >= target_date,
                    Bill.due_date <= widened_end,
                ),
            ),
        )
        .order_by(Bill.bank_code)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def send_payment_reminders(
    session: AsyncSession,
    *,
    today: date | None = None,
    outbox: Outbox | None = None,
) -> dict[str, int]:
    """執行每日付款提醒：查詢 3 天與 1 天到期的未付帳單並發送 Telegram 通知。

    投遞規則（先認領、失敗釋放、未設定不認領）由 :class:`ccas.outbox.Outbox`
    負責；認領紀錄為 ``payment_reminders`` (bill_id, reminder_type) 唯一鍵。

    Args:
        session: 非同步 DB Session。
        today: 基準日（預設為今天）。
        outbox: 通知投遞（測試注入用）；``None`` 時依設定建立。

    Returns:
        ``{"sent": N, "skipped": M}`` 統計。
    """
    if today is None:
        today = date.today()
    if outbox is None:
        outbox = Outbox.from_settings(get_settings(), session)

    if not outbox.configured:
        logger.info("TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID 未設定，跳過付款提醒")
        return {"sent": 0, "skipped": 0}

    bank_names = await fetch_bank_names(session)

    sent = 0
    skipped = 0

    for days_ahead, reminder_type in [(3, "3day"), (1, "1day")]:
        target_date = today + timedelta(days=days_ahead)
        bills = await _fetch_unpaid_bills_due_on(session, target_date)

        for bill in bills:
            bill_id = bill.id
            bank_name = bank_names.get(bill.bank_code, bill.bank_code)
            render = partial(
                render_due_reminder,
                bank_name,
                bill.total_amount,
                bill.due_date,
                bill_id,
                days_ahead,
            )
            outcome = await outbox.deliver(
                PaymentReminderClaim(bill_id, reminder_type), render
            )
            match outcome.status:
                case DeliveryStatus.SENT:
                    sent += 1
                    logger.info(
                        "Sent %s reminder for bill #%d (%s)",
                        reminder_type,
                        bill_id,
                        bank_name,
                    )
                case DeliveryStatus.ALREADY_DELIVERED:
                    skipped += 1
                case DeliveryStatus.FAILED:
                    logger.error(
                        "Failed to send %s reminder for bill #%d: %s",
                        reminder_type,
                        bill_id,
                        outcome.error,
                    )
                case DeliveryStatus.SKIPPED_UNCONFIGURED:
                    pass  # 未設定時已在迴圈前提早返回。

    return {"sent": sent, "skipped": skipped}
