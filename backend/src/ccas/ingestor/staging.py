"""附件 staging 路徑產生、去重複查詢與記錄建立。

負責 staging path 計算（純函式）、dedupe 查詢與
StagedAttachment 記錄的持久化。
不執行檔案系統操作（寫檔由 job.py 負責）。
"""

from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.storage.models import StagedAttachment


def build_staged_path(
    staging_dir: str,
    bank_code: str,
    message_id: str,
    filename: str,
) -> Path:
    """產生 PDF 附件的 staging 落地路徑。

    路徑規則：{staging_dir}/{bank_code}/{message_id[:12]}_{filename}

    Args:
        staging_dir: staging 根目錄。
        bank_code: 銀行代碼（用於子目錄隔離）。
        message_id: Gmail message ID（取前 12 字元避免路徑過長）。
        filename: 原始附件檔名。

    Returns:
        附件的完整 staging 路徑。
    """
    safe_prefix = message_id[:12]
    return Path(staging_dir) / bank_code / f"{safe_prefix}_{filename}"


async def find_existing_staged(
    session: AsyncSession,
    message_id: str,
    attachment_id: str,
) -> StagedAttachment | None:
    """查詢是否已存在相同 Gmail 附件的 staging 記錄。

    使用 (gmail_message_id, gmail_attachment_id) 作為 dedupe 鍵。

    Args:
        session: 非同步 DB Session。
        message_id: Gmail message ID。
        attachment_id: Gmail attachment ID。

    Returns:
        已存在的 StagedAttachment 記錄，若不存在則回傳 None。
    """
    stmt = select(StagedAttachment).where(
        StagedAttachment.gmail_message_id == message_id,
        StagedAttachment.gmail_attachment_id == attachment_id,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def create_staged_record(
    session: AsyncSession,
    *,
    bank_code: str,
    message_id: str,
    attachment_id: str,
    message_date: datetime,
    original_filename: str,
    staged_path: str | None,
    status: str,
    error_reason: str | None = None,
) -> StagedAttachment:
    """建立並持久化一筆 StagedAttachment 記錄。

    Args:
        session: 非同步 DB Session。
        bank_code: 銀行代碼。
        message_id: Gmail message ID。
        attachment_id: Gmail attachment ID。
        message_date: 郵件日期。
        original_filename: 附件原始檔名。
        staged_path: staging 落地路徑（失敗時為 None）。
        status: 處理狀態（"staged" 或 "failed"）。
        error_reason: 失敗原因（成功時為 None）。

    Returns:
        新建的 StagedAttachment 記錄。
    """
    record = StagedAttachment(
        bank_code=bank_code,
        gmail_message_id=message_id,
        gmail_attachment_id=attachment_id,
        message_date=message_date,
        original_filename=original_filename,
        staged_path=staged_path,
        status=status,
        error_reason=error_reason,
    )
    session.add(record)
    await session.flush()
    return record
