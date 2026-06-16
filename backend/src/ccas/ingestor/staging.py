"""附件 staging 的去重複查詢與記錄持久化。

負責 dedupe 查詢與 StagedAttachment 記錄的持久化。
不執行檔案系統操作（寫檔由 job.py 負責）。

純路徑計算（``build_staged_path`` / ``staged_path_for_storage`` /
``resolve_staged_path``）已搬移至 ``ccas.storage.paths``；此處以 re-export
保持既有 import 路徑相容（decryptor/parser job 仍從此模組匯入）。
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.storage.models import StagedAttachment, StagedAttachmentStatus
from ccas.storage.paths import (
    build_staged_path,  # noqa: F401
    resolve_staged_path,  # noqa: F401
    staged_path_for_storage,  # noqa: F401
)


async def find_existing_staged(
    session: AsyncSession,
    message_id: str,
    part_id: str,
    original_filename: str,
) -> StagedAttachment | None:
    """查詢是否已存在相同 Gmail 附件的 staging 記錄。

    使用 (gmail_message_id, gmail_part_id) 作為 stable dedupe 鍵。
    當 part_id 為空字串（例如 Gmail payload 缺 partId 的防禦分支），
    或主查詢無命中但同 message_id 下存在 gmail_part_id 為 NULL 的
    舊資料（migration 前的列）且 original_filename 相符時，會 fallback
    命中該列，讓呼叫端決定是否 backfill part_id。

    Args:
        session: 非同步 DB Session。
        message_id: Gmail message ID。
        part_id: Gmail MIME partId（結構性穩定識別碼）。
        original_filename: 附件原始檔名（fallback 比對用）。

    Returns:
        已存在的 StagedAttachment 記錄，若不存在則回傳 None。
    """
    if part_id:
        primary = select(StagedAttachment).where(
            StagedAttachment.gmail_message_id == message_id,
            StagedAttachment.gmail_part_id == part_id,
        )
        primary_result = await session.execute(primary)
        hit = primary_result.scalar_one_or_none()
        if hit is not None:
            return hit

    fallback = (
        select(StagedAttachment)
        .where(
            StagedAttachment.gmail_message_id == message_id,
            StagedAttachment.gmail_part_id.is_(None),
            StagedAttachment.original_filename == original_filename,
        )
        .order_by(StagedAttachment.id.desc())
        .limit(1)
    )
    fallback_result = await session.execute(fallback)
    return fallback_result.scalar_one_or_none()


async def backfill_part_id(
    session: AsyncSession,
    record: StagedAttachment,
    part_id: str,
) -> None:
    """回填舊紀錄的 gmail_part_id 欄位（migration 後漸進式補齊）。

    只在 record.gmail_part_id 為 None 且新 part_id 非空字串時寫入。
    用於 find_existing_staged fallback 命中後的 opportunistic backfill。
    """
    if not part_id or record.gmail_part_id is not None:
        return
    record.gmail_part_id = part_id
    session.add(record)
    await session.flush()


async def create_staged_record(
    session: AsyncSession,
    *,
    bank_code: str,
    message_id: str,
    attachment_id: str,
    message_date: datetime,
    original_filename: str,
    staged_path: str | None,
    status: StagedAttachmentStatus,
    error_reason: str | None = None,
    source_type: str = "attachment",
    part_id: str = "",
) -> StagedAttachment:
    """建立並持久化一筆 StagedAttachment 記錄。

    Args:
        session: 非同步 DB Session。
        bank_code: 銀行代碼。
        message_id: Gmail message ID。
        attachment_id: Gmail attachment ID（非穩定、僅保留以供下載）。
        message_date: 郵件日期。
        original_filename: 附件原始檔名。
        staged_path: staging 落地路徑（失敗時為 None）。
        status: 處理狀態（"staged" 或 "failed"）。
        error_reason: 失敗原因（成功時為 None）。
        source_type: 來源類型（"attachment" 或 "web_fetch"）。
        part_id: Gmail MIME partId（穩定 dedupe 鍵）；空字串會寫入 NULL。

    Returns:
        新建的 StagedAttachment 記錄。
    """
    record = StagedAttachment(
        bank_code=bank_code,
        gmail_message_id=message_id,
        gmail_attachment_id=attachment_id,
        gmail_part_id=part_id if part_id else None,
        message_date=message_date,
        original_filename=original_filename,
        staged_path=staged_path,
        status=status,
        error_reason=error_reason,
        source_type=source_type,
    )
    session.add(record)
    await session.flush()
    return record


async def update_staged_record_failure(
    session: AsyncSession,
    record: StagedAttachment,
    *,
    status: StagedAttachmentStatus,
    error_reason: str,
) -> None:
    """更新既有 StagedAttachment 的狀態與錯誤原因（失敗路徑使用）。

    當自動重試（is_failed_retry）再次失敗時，既有紀錄應被更新為最新的
    狀態/錯誤，而不是保留上一次的陳舊值。亦用於把 ``failed`` 轉為
    ``fetch_expired`` 這類語意升級。

    Args:
        session: 非同步 DB Session。
        record: 目標 StagedAttachment。
        status: 新狀態（例：``failed``、``fetch_expired``）。
        error_reason: 新錯誤描述。
    """
    record.status = status
    record.error_reason = error_reason
    session.add(record)
    await session.flush()


async def delete_staged_record(
    session: AsyncSession,
    record: StagedAttachment,
) -> None:
    """刪除既有的 StagedAttachment 記錄。

    用於 force 模式：先刪舊記錄再重新下載。
    不處理磁碟檔案清理（由呼叫端負責）。

    Args:
        session: 非同步 DB Session。
        record: 要刪除的 staging 記錄。
    """
    await session.delete(record)
    await session.flush()
