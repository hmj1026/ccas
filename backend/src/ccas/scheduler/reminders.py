"""付款提醒排程工作。

查詢未付帳單並透過 Telegram 發送到期前 3 天與 1 天的提醒。
以 (bill_id, reminder_type) 唯一鍵防止重複發送。
"""

import logging
from datetime import date, timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, and_, delete, or_, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.config import get_settings
from ccas.messaging import render_due_reminder, send_message
from ccas.storage.models import Bill, PaymentReminder
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


async def _claim_reminder(
    session: AsyncSession,
    bill_id: int,
    reminder_type: str,
) -> bool:
    """先 claim 後送：原子 INSERT 取得發送權，回傳是否由本次成功 claim。

    以 ``INSERT ... ON CONFLICT DO NOTHING`` + commit 搶占 (bill_id, reminder_type)
    唯一鍵。``rowcount > 0`` 表示本次新建（取得發送權）；``0`` 表示已有人 claim
    過（先前已送或並行 worker 搶先），應跳過。先 claim 再送可避免「送出成功但
    記錄失敗 → 下次重送」的舊有 race（R21）。
    """
    stmt = (
        sqlite_insert(PaymentReminder)
        .values(bill_id=bill_id, reminder_type=reminder_type)
        .on_conflict_do_nothing(index_elements=["bill_id", "reminder_type"])
    )
    result = cast(CursorResult[Any], await session.execute(stmt))
    await session.commit()
    return result.rowcount > 0


async def _release_reminder(
    session: AsyncSession,
    bill_id: int,
    reminder_type: str,
) -> None:
    """送出失敗時釋放先前的 claim，讓下次排程可重試（避免提醒永久遺失）。"""
    await session.execute(
        delete(PaymentReminder).where(
            PaymentReminder.bill_id == bill_id,
            PaymentReminder.reminder_type == reminder_type,
        )
    )
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
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        logger.info("TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID 未設定，跳過付款提醒")
        return {"sent": 0, "skipped": 0}

    bank_names = await fetch_bank_names(session)

    sent = 0
    skipped = 0

    for days_ahead, reminder_type in [(3, "3day"), (1, "1day")]:
        target_date = today + timedelta(days=days_ahead)
        bills = await _fetch_unpaid_bills_due_on(session, target_date)

        for bill in bills:
            # 先 claim：搶不到（已送 / 並行搶先）就跳過。
            if not await _claim_reminder(session, bill.id, reminder_type):
                skipped += 1
                continue

            bank_name = bank_names.get(bill.bank_code, bill.bank_code)
            try:
                text = render_due_reminder(bill, bank_name, days_ahead)
                await send_message(
                    settings.telegram_bot_token, settings.telegram_chat_id, text
                )
                sent += 1
                logger.info(
                    "Sent %s reminder for bill #%d (%s)",
                    reminder_type,
                    bill.id,
                    bank_name,
                )
            except Exception as exc:
                # 送出失敗 → 釋放 claim，讓下次排程重試。
                await _release_reminder(session, bill.id, reminder_type)
                logger.error(
                    "Failed to send %s reminder for bill #%d: %s",
                    reminder_type,
                    bill.id,
                    exc,
                )

    return {"sent": sent, "skipped": skipped}
