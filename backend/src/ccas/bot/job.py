"""批次通知 job 入口模組。

提供 run_notify_job() 作為 pipeline 的通知階段，
自動查詢未通知帳單並發送 Telegram 通知。
"""

import logging
from dataclasses import dataclass, field
from typing import Any, cast

from sqlalchemy import CursorResult, select
from sqlalchemy import update as sa_update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.config import get_settings
from ccas.messaging import render_new_bill_notification, send_message
from ccas.pipeline.progress import NoopProgressReporter, ProgressReporter
from ccas.storage.models import Bill, PaymentReminder
from ccas.storage.queries import fetch_bank_names

logger = logging.getLogger(__name__)

# reminder_type used to dedupe new-bill notifications; must not collide with
# scheduler reminder types ("3day" / "1day") in scheduler/reminders.py.
NEW_BILL_REMINDER_TYPE = "new_bill"


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
    reporter: ProgressReporter | None = None,
) -> NotifySummary:
    """查詢未通知帳單並發送 Telegram 通知。

    自動查詢 is_notified=False 的帳單，發送成功後標記為已通知。
    發送前先以 PaymentReminder (bill_id, "new_bill") 唯一鍵 claim，
    確保重複執行不會重複發送（at-most-once）。

    Args:
        session: 非同步 DB Session。
        reporter: 進度回報（pipeline-operations-center §3A.5）。``None``
            時走 NoopProgressReporter。

    Returns:
        NotifySummary 統計摘要。
    """
    if reporter is None:
        reporter = NoopProgressReporter()

    summary = NotifySummary()

    settings = get_settings()
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        logger.info("TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID 未設定，跳過 notify stage")
        await reporter.stage_started("notify", total=0)
        return summary

    stmt = select(Bill).where(Bill.is_notified.is_(False))
    result = await session.execute(stmt)
    bills = list(result.scalars().all())

    if not bills:
        logger.info("沒有未通知的帳單，跳過通知")
        await reporter.stage_started("notify", total=0)
        return summary

    bank_names = await fetch_bank_names(session)

    # Pre-extract all scalar attributes before any session.commit/rollback to avoid
    # lazy-loading expired ORM objects (MissingGreenlet) on subsequent iterations.
    bill_rows = [
        (b.id, b.bank_code, b.billing_month, b.total_amount, b.due_date) for b in bills
    ]

    await reporter.stage_started("notify", total=len(bill_rows))
    processed = 0
    for bill_id, bill_code, bill_month, bill_total, bill_due in bill_rows:
        try:
            # Idempotency guard (same insert-first pattern as
            # scheduler/reminders.py): claim the bill via the
            # (bill_id, reminder_type) unique key BEFORE sending, so a crash
            # between send and is_notified update can never double-send.
            insert_stmt = (
                sqlite_insert(PaymentReminder)
                .values(bill_id=bill_id, reminder_type=NEW_BILL_REMINDER_TYPE)
                .on_conflict_do_nothing(index_elements=["bill_id", "reminder_type"])
            )
            insert_result = cast(CursorResult[Any], await session.execute(insert_stmt))
            await session.commit()
            if insert_result.rowcount == 0:
                # Already claimed by a previous run (is_notified update must
                # have failed last time); skip without sending again and
                # repair the flag so the bill stops being re-scanned.
                logger.info(
                    "通知已發送過，跳過: bill #%d (%s/%s)",
                    bill_id,
                    bill_code,
                    bill_month,
                )
                await session.execute(
                    sa_update(Bill).where(Bill.id == bill_id).values(is_notified=True)
                )
                await session.commit()
                continue

            bank_name = bank_names.get(bill_code, bill_code)
            text = render_new_bill_notification(
                bank_name, bill_month, bill_total, bill_due
            )
            await send_message(
                settings.telegram_bot_token, settings.telegram_chat_id, text
            )
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
        else:
            # Mark notified after a successful send. Failure here is
            # tolerable: idempotency is carried by the PaymentReminder
            # unique key, so the next run skips instead of re-sending.
            try:
                # UPDATE query avoids touching expired ORM objects.
                await session.execute(
                    sa_update(Bill).where(Bill.id == bill_id).values(is_notified=True)
                )
                await session.commit()
            except Exception:
                await session.rollback()
                logger.exception(
                    "is_notified 更新失敗 (bill #%d)，下次執行將以 "
                    "PaymentReminder 唯一鍵跳過",
                    bill_id,
                )
        finally:
            processed += 1
            try:
                await reporter.stage_item_done("notify", processed=processed)
            except Exception:
                logger.warning(
                    "notify progress reporting failed (processed=%d); continuing",
                    processed,
                    exc_info=True,
                )

    return summary
