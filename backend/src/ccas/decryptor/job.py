"""批次 PDF 解密 job 入口模組。

提供 run_decryption_job() 作為批次處理入口，
逐一處理所有狀態為 staged 的附件。
單筆失敗不會中止整個 batch。
"""

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from ccas.config import get_settings
from ccas.decryptor.decrypt import DecryptionError, decrypt_pdf
from ccas.decryptor.password import resolve_password
from ccas.decryptor.staging import fetch_pending_attachments, update_attachment_status
from ccas.storage.models import StagedAttachment

logger = logging.getLogger(__name__)


@dataclass
class DecryptionSummary:
    """單次解密 batch 的統計摘要。

    Attributes:
        decrypted_count: 成功解密的加密 PDF 數。
        passthrough_count: 未加密直接透通的 PDF 數。
        skipped_count: 已為 decrypted 狀態而略過的數量。
        failed_count: 解密失敗的數量。
        errors: 錯誤訊息清單。
    """

    decrypted_count: int = 0
    passthrough_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    errors: list[str] = field(default_factory=list)


async def _process_attachment(
    attachment: StagedAttachment,
    session: AsyncSession,
    summary: DecryptionSummary,
) -> None:
    """處理單一附件的解密。"""
    settings = get_settings()
    password = resolve_password(settings, attachment.bank_code)

    try:
        result = await asyncio.to_thread(
            decrypt_pdf, Path(attachment.staged_path), password  # type: ignore[arg-type]
        )
    except DecryptionError as exc:
        error_msg = (
            f"解密失敗 ({attachment.bank_code}/{attachment.original_filename}): {exc}"
        )
        summary.failed_count += 1
        summary.errors.append(error_msg)
        logger.error(error_msg)
        await update_attachment_status(
            session, attachment, status="decrypt_failed", error_reason=str(exc)
        )
        return
    except Exception as exc:
        error_msg = (
            f"解密異常 ({attachment.bank_code}/{attachment.original_filename}): {exc}"
        )
        summary.failed_count += 1
        summary.errors.append(error_msg)
        logger.error(error_msg)
        await update_attachment_status(
            session, attachment, status="decrypt_failed", error_reason=str(exc)
        )
        return

    if result.needed_decryption:
        summary.decrypted_count += 1
        logger.info(
            "已解密附件：%s/%s",
            attachment.bank_code,
            attachment.original_filename,
        )
    else:
        summary.passthrough_count += 1
        logger.info(
            "附件未加密，透通：%s/%s",
            attachment.bank_code,
            attachment.original_filename,
        )

    await update_attachment_status(session, attachment, status="decrypted")


async def run_decryption_job(session: AsyncSession) -> DecryptionSummary:
    """執行單次批次 PDF 解密。

    流程：
    1. 查詢所有狀態為 staged 的附件
    2. 逐一嘗試解密，更新 staging 狀態
    3. 單筆失敗不中止整個批次
    4. 回傳統計摘要

    Args:
        session: 非同步 DB Session（由呼叫端注入）。

    Returns:
        DecryptionSummary 統計摘要。
    """
    summary = DecryptionSummary()

    attachments = await fetch_pending_attachments(session)
    if not attachments:
        logger.info("沒有待解密的附件，跳過 decryption")
        return summary

    for attachment in attachments:
        await _process_attachment(attachment, session, summary)

    await session.commit()

    logger.info(
        "Decryption 完成：%d 解密, %d 透通, %d 略過, %d 失敗",
        summary.decrypted_count,
        summary.passthrough_count,
        summary.skipped_count,
        summary.failed_count,
    )

    return summary
