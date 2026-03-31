"""付款提醒排程工作。

查詢未付帳單並透過 Telegram 發送到期前 3 天與 1 天的提醒。
以 (bill_id, reminder_type) 唯一鍵防止重複發送。
"""

import logging
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.bot.client import send_message
from ccas.bot.notifications import render_due_reminder
from ccas.config import get_settings
from ccas.storage.models import Bill, BankConfig, PaymentReminder

logger = logging.getLogger(__name__)


async def _fetch_bank_names(session: AsyncSession) -> dict[str, str]:
    stmt = select(BankConfig.bank_code, BankConfig.bank_name)
    result = await session.execute(stmt)
    return {row[0]: row[1] for row in result.all()}


async def _fetch_unpaid_bills_due_on(
    session: AsyncSession,
    target_date: date,
) -> list[Bill]:
    """查詢到期日為指定日期且未付的帳單。"""
    stmt = (
        select(Bill)
        .where(
            Bill.is_paid.is_(False),
            Bill.due_date == target_date,
        )
        .order_by(Bill.bank_code)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def _already_reminded(
    session: AsyncSession,
    bill_id: int,
    reminder_type: str,
) -> bool:
    """檢查是否已發送過此類型提醒。"""
    stmt = select(PaymentReminder.id).where(
        PaymentReminder.bill_id == bill_id,
        PaymentReminder.reminder_type == reminder_type,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


async def _record_reminder(
    session: AsyncSession,
    bill_id: int,
    reminder_type: str,
) -> None:
    """記錄已發送的提醒（使用 INSERT OR IGNORE 防止並行衝突）。"""
    stmt = (
        sqlite_insert(PaymentReminder)
        .values(bill_id=bill_id, reminder_type=reminder_type)
        .on_conflict_do_nothing(index_elements=["bill_id", "reminder_type"])
    )
    await session.execute(stmt)
    await session.commit()


async def send_payment_reminders(
    session: AsyncSession,
    *,
    today: date | None = None,
) -> dict[str, int]:
    """執行每日付款提醒：查詢 3 天與 1 天到期的未付帳單並發送 Telegram 通知。

    Args:
        session: 非同步 DB Session。
        today: 基準日（預設為今天）。

    Returns:
        ``{"sent": N, "skipped": M}`` 統計。
    """
    if today is None:
        today = date.today()

    settings = get_settings()
    bank_names = await _fetch_bank_names(session)

    sent = 0
    skipped = 0

    for days_ahead, reminder_type in [(3, "3day"), (1, "1day")]:
        target_date = today + timedelta(days=days_ahead)
        bills = await _fetch_unpaid_bills_due_on(session, target_date)

        for bill in bills:
            if await _already_reminded(session, bill.id, reminder_type):
                skipped += 1
                continue

            bank_name = bank_names.get(bill.bank_code, bill.bank_code)
            try:
                text = render_due_reminder(bill, bank_name, days_ahead)
                await send_message(
                    settings.telegram_bot_token, settings.telegram_chat_id, text
                )
                await _record_reminder(session, bill.id, reminder_type)
                sent += 1
                logger.info(
                    "Sent %s reminder for bill #%d (%s)",
                    reminder_type,
                    bill.id,
                    bank_name,
                )
            except Exception as exc:
                logger.error(
                    "Failed to send %s reminder for bill #%d: %s",
                    reminder_type,
                    bill.id,
                    exc,
                )

    return {"sent": sent, "skipped": skipped}
