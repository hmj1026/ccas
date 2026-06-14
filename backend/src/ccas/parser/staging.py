"""Parser 流程的 staging 資料存取層。

提供查詢待解析附件、更新附件狀態、
以及建立 Bill/Transaction 記錄的函式。
"""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.parser.result import ParseResult
from ccas.pipeline.filters import apply_pipeline_filters
from ccas.pipeline.options import PipelineOptions
from ccas.storage.models import (
    BankConfig,
    Bill,
    PaymentReminder,
    StagedAttachment,
    StagedAttachmentStatus,
    Transaction,
)


async def fetch_parseable_attachments(
    session: AsyncSession,
    options: PipelineOptions | None = None,
) -> Sequence[StagedAttachment]:
    """查詢待解析附件，可依 options 篩選。

    正常模式僅查詢 ``decrypted``；force 模式額外包含
    ``parsed``、``parse_failed``、``parse_skipped``，允許重新解析。

    Args:
        session: 非同步 DB Session。
        options: Pipeline 選項（bank_code / date range / force 篩選）。

    Returns:
        待解析的 StagedAttachment 記錄清單。
    """
    force = options.force if options else False
    if force:
        stmt = select(StagedAttachment).where(
            StagedAttachment.status.in_(
                [
                    StagedAttachmentStatus.DECRYPTED,
                    StagedAttachmentStatus.PARSED,
                    StagedAttachmentStatus.PARSE_FAILED,
                    StagedAttachmentStatus.PARSE_SKIPPED,
                ]
            )
        )
    else:
        stmt = select(StagedAttachment).where(
            StagedAttachment.status == StagedAttachmentStatus.DECRYPTED
        )
    stmt = apply_pipeline_filters(stmt, options)
    result = await session.execute(stmt)
    return result.scalars().all()


async def get_bank_config(session: AsyncSession, bank_code: str) -> BankConfig | None:
    """依 bank_code 取得銀行設定。

    Args:
        session: 非同步 DB Session。
        bank_code: 銀行代碼。

    Returns:
        BankConfig 記錄，不存在則回傳 None。
    """
    stmt = select(BankConfig).where(BankConfig.bank_code == bank_code)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def check_bill_exists(
    session: AsyncSession, bank_code: str, billing_month: str
) -> bool:
    """檢查某銀行某月份的帳單是否已存在。

    Args:
        session: 非同步 DB Session。
        bank_code: 銀行代碼。
        billing_month: 帳單月份（如 "2026-03"）。

    Returns:
        True 表示帳單已存在。
    """
    stmt = select(Bill.id).where(
        Bill.bank_code == bank_code,
        Bill.billing_month == billing_month,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


async def delete_existing_bill(
    session: AsyncSession,
    bank_code: str,
    billing_month: str,
) -> bool:
    """刪除指定銀行月份的既有帳單及關聯資料。

    用於 force 模式：先刪除舊帳單再重新解析。
    刪除順序：PaymentReminder -> Bill (cascade Transaction)。

    Args:
        session: 非同步 DB Session。
        bank_code: 銀行代碼。
        billing_month: 帳單月份。

    Returns:
        True 表示有刪除舊帳單，False 表示不存在。
    """
    stmt = select(Bill).where(
        Bill.bank_code == bank_code,
        Bill.billing_month == billing_month,
    )
    result = await session.execute(stmt)
    bill = result.scalar_one_or_none()

    if bill is None:
        return False

    # Delete associated payment reminders first (no cascade on FK)
    reminder_stmt = select(PaymentReminder).where(PaymentReminder.bill_id == bill.id)
    reminder_result = await session.execute(reminder_stmt)
    for reminder in reminder_result.scalars().all():
        await session.delete(reminder)

    # Delete bill (cascade deletes transactions)
    await session.delete(bill)
    await session.flush()
    return True


async def create_bill_and_transactions(
    session: AsyncSession,
    parse_result: ParseResult,
    file_path: str | None = None,
) -> Bill:
    """根據 ParseResult 建立 Bill 與 Transaction 記錄。

    Args:
        session: 非同步 DB Session。
        parse_result: Parser 解析結果。
        file_path: 原始 PDF 檔案路徑。

    Returns:
        新建立的 Bill 記錄。
    """
    bill = Bill(
        bank_code=parse_result.bank_code,
        billing_month=parse_result.billing_month,
        total_amount=parse_result.total_amount,
        due_date=parse_result.due_date,
        file_path=file_path,
    )
    session.add(bill)
    await session.flush()

    for item in parse_result.transactions:
        txn = Transaction(
            bill_id=bill.id,
            trans_date=item.trans_date,
            posting_date=item.posting_date,
            merchant=item.merchant,
            amount=item.amount,
            currency=item.currency,
            original_amount=item.original_amount,
            card_last4=item.card_last4,
            installment_current=item.installment_current,
            installment_total=item.installment_total,
        )
        session.add(txn)

    await session.flush()
    return bill


async def update_attachment_status(
    session: AsyncSession,
    attachment: StagedAttachment,
    *,
    status: StagedAttachmentStatus,
    error_reason: str | None = None,
) -> None:
    """更新附件的處理狀態。

    Args:
        session: 非同步 DB Session。
        attachment: 要更新的 StagedAttachment 記錄。
        status: 新狀態值（如 ``parsed``、``parse_failed``）。
        error_reason: 失敗原因（成功時傳入 None 以清除既有錯誤）。
    """
    attachment.status = status
    attachment.error_reason = error_reason
    await session.flush()
