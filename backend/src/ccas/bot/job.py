"""批次通知 job 入口模組。

提供 run_notify_job() 作為 pipeline 的通知階段，
自動查詢未通知帳單並發送 Telegram 通知。
"""

import logging
from datetime import date
from functools import partial
from typing import NamedTuple

from sqlalchemy import select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.config import get_settings
from ccas.messaging import (
    ParseFailureLine,
    render_new_bill_notification,
    render_parse_failure_notification,
)
from ccas.outbox import (
    DeliveryStatus,
    Outbox,
    ParseFailureClaim,
    PaymentReminderClaim,
)
from ccas.pipeline.summary import NotifySummary
from ccas.services.identity import sanitize_text
from ccas.shared.progress import NoopProgressReporter, ProgressReporter
from ccas.storage.models import Bill, StagedAttachment, StagedAttachmentStatus
from ccas.storage.queries import fetch_bank_names

logger = logging.getLogger(__name__)

# reminder_type used to dedupe new-bill notifications; must not collide with
# scheduler reminder types ("3day" / "1day") in scheduler/reminders.py.
NEW_BILL_REMINDER_TYPE = "new_bill"

# NotifySummary 已移至 ccas.pipeline.summary（解除 pipeline→bot 反向相依）；
# 此處 re-export 維持既有 ``from ccas.bot.job import NotifySummary`` 路徑。
__all__ = ["NEW_BILL_REMINDER_TYPE", "NotifySummary", "run_notify_job"]

_BillRow = tuple[int, str, str, int, date | None]


class _ParseFailure(NamedTuple):
    id: int
    bank_code: str
    original_filename: str
    error_reason: str | None


async def run_notify_job(
    session: AsyncSession,
    reporter: ProgressReporter | None = None,
    *,
    outbox: Outbox | None = None,
) -> NotifySummary:
    """查詢未通知帳單並發送 Telegram 通知。

    1. 新帳單通知：查詢 is_notified=False 的帳單，發送成功後標記為已通知；
       認領紀錄為 PaymentReminder (bill_id, "new_bill") 唯一鍵。
    2. 解析失敗通知：狀態為 parse_failed 且尚未通知（failure_notified_at 為空）
       的帳單附件合併為一則訊息；parser 之後重試仍失敗也不重送。

    投遞規則由 :class:`ccas.outbox.Outbox` 負責：成功送出的通知不會重送；
    發送失敗會釋放認領，下次執行重試。

    Args:
        session: 非同步 DB Session。
        reporter: 進度回報（pipeline-operations-center §3A.5）。``None``
            時走 NoopProgressReporter。
        outbox: 通知投遞（測試注入用）；``None`` 時依設定建立。

    Returns:
        NotifySummary 統計摘要。
    """
    if reporter is None:
        reporter = NoopProgressReporter()
    if outbox is None:
        outbox = Outbox.from_settings(get_settings(), session)

    summary = NotifySummary()

    if not outbox.configured:
        logger.info("TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID 未設定，跳過 notify stage")
        await reporter.stage_started("notify", total=0)
        return summary

    stmt = select(Bill).where(Bill.is_notified.is_(False))
    bills = list((await session.execute(stmt)).scalars().all())
    failures = await _fetch_unnotified_parse_failures(session)

    if not bills and not failures:
        logger.info("沒有未通知的帳單或解析失敗，跳過通知")
        await reporter.stage_started("notify", total=0)
        return summary

    bank_names = await fetch_bank_names(session)

    # Pre-extract all scalar attributes before any session.commit/rollback to avoid
    # lazy-loading expired ORM objects (MissingGreenlet) on subsequent iterations.
    bill_rows: list[_BillRow] = [
        (b.id, b.bank_code, b.billing_month, b.total_amount, b.due_date) for b in bills
    ]

    # 解析失敗合併為一則訊息，計為一個 notify 項目。
    total = len(bill_rows) + (1 if failures else 0)
    await reporter.stage_started("notify", total=total)
    processed = 0
    for row in bill_rows:
        await _notify_new_bill(session, outbox, summary, row, bank_names)
        processed += 1
        await _report_item_done(reporter, processed)
    if failures:
        await _notify_parse_failures(outbox, summary, failures, bank_names)
        processed += 1
        await _report_item_done(reporter, processed)

    return summary


async def _notify_new_bill(
    session: AsyncSession,
    outbox: Outbox,
    summary: NotifySummary,
    row: _BillRow,
    bank_names: dict[str, str],
) -> None:
    bill_id, bill_code, bill_month, bill_total, bill_due = row
    render = partial(
        render_new_bill_notification,
        bank_names.get(bill_code, bill_code),
        bill_month,
        bill_total,
        bill_due,
    )
    outcome = await outbox.deliver(
        PaymentReminderClaim(bill_id, NEW_BILL_REMINDER_TYPE), render
    )
    match outcome.status:
        case DeliveryStatus.SENT:
            summary.sent_count += 1
            logger.info("通知成功: bill #%d (%s/%s)", bill_id, bill_code, bill_month)
            await _mark_notified(session, bill_id)
        case DeliveryStatus.ALREADY_DELIVERED:
            # 認領已存在：先前已送出但 is_notified 更新遺失，或先前釋放認領失敗
            # （已由 Outbox 記錄）。不再發送，補上旗標讓帳單不再被重複掃描。
            logger.info(
                "通知 claim 已存在，跳過: bill #%d (%s/%s)",
                bill_id,
                bill_code,
                bill_month,
            )
            await _mark_notified(session, bill_id)
        case DeliveryStatus.FAILED:
            _record_failure(summary, f"bill #{bill_id}", outcome.error)
        case DeliveryStatus.SKIPPED_UNCONFIGURED:
            pass  # run_notify_job 已在未設定時提早返回。


async def _mark_notified(session: AsyncSession, bill_id: int) -> None:
    """標記 is_notified；失敗可容忍：認領保留，下次執行判定為已投遞而跳過。"""
    try:
        # UPDATE query avoids touching expired ORM objects.
        await session.execute(
            sa_update(Bill).where(Bill.id == bill_id).values(is_notified=True)
        )
        await session.commit()
    except Exception:
        await session.rollback()
        logger.exception(
            "is_notified 更新失敗 (bill #%d)，下次執行將以 PaymentReminder 唯一鍵跳過",
            bill_id,
        )


async def _fetch_unnotified_parse_failures(
    session: AsyncSession,
) -> list[_ParseFailure]:
    stmt = (
        select(
            StagedAttachment.id,
            StagedAttachment.bank_code,
            StagedAttachment.original_filename,
            StagedAttachment.error_reason,
        )
        .where(
            StagedAttachment.status == StagedAttachmentStatus.PARSE_FAILED,
            StagedAttachment.failure_notified_at.is_(None),
        )
        .order_by(StagedAttachment.id)
    )
    return [_ParseFailure(*row) for row in (await session.execute(stmt)).all()]


async def _notify_parse_failures(
    outbox: Outbox,
    summary: NotifySummary,
    failures: list[_ParseFailure],
    bank_names: dict[str, str],
) -> None:
    by_id = {row.id: row for row in failures}
    claim = ParseFailureClaim(list(by_id))

    def render() -> str:
        # 只列出本次實際認領的附件；失敗原因可能含 PDF 內容片段，遮罩卡號與憑證。
        return render_parse_failure_notification(
            [
                ParseFailureLine(
                    bank_names.get(row.bank_code, row.bank_code),
                    row.original_filename,
                    sanitize_text(row.error_reason) or None,
                )
                for row in (by_id[i] for i in claim.claimed_ids)
            ]
        )

    outcome = await outbox.deliver(claim, render)
    match outcome.status:
        case DeliveryStatus.SENT:
            summary.sent_count += 1
            logger.info("解析失敗通知成功: %d 份附件", len(claim.claimed_ids))
        case DeliveryStatus.FAILED:
            _record_failure(summary, "parse failures", outcome.error)
        case DeliveryStatus.ALREADY_DELIVERED | DeliveryStatus.SKIPPED_UNCONFIGURED:
            pass  # 已由其他執行認領，或 Telegram 未設定（已提早返回）。


def _record_failure(
    summary: NotifySummary, subject: str, error: Exception | None
) -> None:
    error_msg = f"通知失敗 ({subject}): {error}"
    summary.failed_count += 1
    summary.errors.append(error_msg)
    logger.error(error_msg)


async def _report_item_done(reporter: ProgressReporter, processed: int) -> None:
    try:
        await reporter.stage_item_done("notify", processed=processed)
    except Exception:
        logger.warning(
            "notify progress reporting failed (processed=%d); continuing",
            processed,
            exc_info=True,
        )
