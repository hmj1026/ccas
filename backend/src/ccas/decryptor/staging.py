"""解密流程的 staging 資料存取層。

提供查詢待解密附件與更新附件狀態的函式。
"""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.storage.models import StagedAttachment


async def fetch_pending_attachments(
    session: AsyncSession,
) -> Sequence[StagedAttachment]:
    """查詢所有狀態為 ``staged`` 的附件。

    Args:
        session: 非同步 DB Session。

    Returns:
        待解密的 StagedAttachment 記錄清單。
    """
    stmt = select(StagedAttachment).where(StagedAttachment.status == "staged")
    result = await session.execute(stmt)
    return result.scalars().all()


async def update_attachment_status(
    session: AsyncSession,
    attachment: StagedAttachment,
    *,
    status: str,
    error_reason: str | None = None,
) -> None:
    """更新附件的處理狀態。

    Args:
        session: 非同步 DB Session。
        attachment: 要更新的 StagedAttachment 記錄。
        status: 新狀態值（如 ``decrypted``、``decrypt_failed``）。
        error_reason: 失敗原因（成功時傳入 None 以清除既有錯誤）。
    """
    attachment.status = status
    attachment.error_reason = error_reason
    await session.flush()
