"""解密流程的 staging 資料存取層。

提供查詢待解密附件與更新附件狀態的函式。
"""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.pipeline.filters import apply_pipeline_filters
from ccas.pipeline.options import PipelineOptions
from ccas.storage.models import StagedAttachment, StagedAttachmentStatus


async def fetch_pending_attachments(
    session: AsyncSession,
    options: PipelineOptions | None = None,
) -> Sequence[StagedAttachment]:
    """查詢待解密附件，可依 options 篩選。

    正常模式僅查詢 ``staged``；force 模式額外包含
    ``decrypted`` 和 ``decrypt_failed``，允許重新解密。

    Args:
        session: 非同步 DB Session。
        options: Pipeline 選項（bank_code / date range / force 篩選）。

    Returns:
        待解密的 StagedAttachment 記錄清單。
    """
    force = options.force if options else False
    if force:
        stmt = select(StagedAttachment).where(
            StagedAttachment.status.in_(
                [
                    StagedAttachmentStatus.STAGED,
                    StagedAttachmentStatus.DECRYPTED,
                    StagedAttachmentStatus.DECRYPT_FAILED,
                ]
            )
        )
    else:
        stmt = select(StagedAttachment).where(
            StagedAttachment.status == StagedAttachmentStatus.STAGED
        )
    stmt = apply_pipeline_filters(stmt, options)
    result = await session.execute(stmt)
    return result.scalars().all()


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
        status: 新狀態值（如 ``decrypted``、``decrypt_failed``）。
        error_reason: 失敗原因（成功時傳入 None 以清除既有錯誤）。
    """
    attachment.status = status
    attachment.error_reason = error_reason
    await session.flush()
