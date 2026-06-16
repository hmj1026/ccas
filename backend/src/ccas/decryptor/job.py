"""批次 PDF 解密 job 入口模組。

提供 run_decryption_job() 作為批次處理入口，
逐一處理所有狀態為 staged 的附件。
單筆失敗不會中止整個 batch。
"""

import asyncio
import logging
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from ccas.config import get_settings
from ccas.decryptor.decrypt import DecryptionError, decrypt_pdf_multi
from ccas.decryptor.password import resolve_passwords
from ccas.decryptor.staging import fetch_pending_attachments, update_attachment_status
from ccas.errors import DecryptError
from ccas.ingestor.staging import resolve_staged_path
from ccas.pipeline.options import PipelineOptions
from ccas.pipeline.progress import NoopProgressReporter, ProgressReporter
from ccas.storage.models import StagedAttachment, StagedAttachmentStatus

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
    passwords: tuple[str, ...],
) -> None:
    """處理單一附件的解密。

    ``passwords`` 由呼叫端的 per-bank 快取預先解析後傳入（避免每筆附件
    重複 Fernet 解密）。密碼解析失敗的銀行已在外層被跳過，不會進到這裡。
    """
    settings = get_settings()
    raw_path = attachment.staged_path

    if raw_path is None:
        error_msg = (
            f"缺少 staged_path，無法解密 ({attachment.bank_code}/"
            f"{attachment.original_filename})"
        )
        summary.failed_count += 1
        summary.errors.append(error_msg)
        logger.error(error_msg)
        await update_attachment_status(
            session,
            attachment,
            status=StagedAttachmentStatus.DECRYPT_FAILED,
            error_reason=error_msg,
        )
        return

    try:
        staged_path = resolve_staged_path(settings.staging_dir, raw_path)
    except ValueError:
        error_msg = (
            f"staged_path 逃逸 staging 根目錄 ({attachment.bank_code}/"
            f"{attachment.original_filename}): {raw_path}"
        )
        summary.failed_count += 1
        summary.errors.append(error_msg)
        logger.error(error_msg)
        await update_attachment_status(
            session,
            attachment,
            status=StagedAttachmentStatus.DECRYPT_FAILED,
            error_reason=error_msg,
        )
        return

    try:
        result = await asyncio.to_thread(
            decrypt_pdf_multi,
            staged_path,
            passwords,
        )
    except DecryptionError as exc:
        error_msg = (
            f"解密失敗 ({attachment.bank_code}/{attachment.original_filename}): {exc}"
        )
        summary.failed_count += 1
        summary.errors.append(error_msg)
        logger.error(error_msg)
        await update_attachment_status(
            session,
            attachment,
            status=StagedAttachmentStatus.DECRYPT_FAILED,
            error_reason=str(exc),
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
            session,
            attachment,
            status=StagedAttachmentStatus.DECRYPT_FAILED,
            error_reason=str(exc),
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

    await update_attachment_status(
        session, attachment, status=StagedAttachmentStatus.DECRYPTED
    )


async def run_decryption_job(
    session: AsyncSession,
    options: PipelineOptions | None = None,
    reporter: ProgressReporter | None = None,
) -> DecryptionSummary:
    """執行單次批次 PDF 解密。

    流程：
    1. 查詢所有狀態為 staged 的附件（依 options 篩選）
    2. 逐一嘗試解密，更新 staging 狀態
    3. 單筆失敗不中止整個批次
    4. 回傳統計摘要

    Args:
        session: 非同步 DB Session（由呼叫端注入）。
        options: Pipeline 選項（bank_code / date range 篩選）。
        reporter: 進度回報（pipeline-operations-center §3A.2）。``None``
            時走 NoopProgressReporter。

    Returns:
        DecryptionSummary 統計摘要。
    """
    if reporter is None:
        reporter = NoopProgressReporter()

    summary = DecryptionSummary()

    attachments = await fetch_pending_attachments(session, options)
    await reporter.stage_started("decrypt", total=len(attachments))
    if not attachments:
        logger.info("沒有待解密的附件，跳過 decryption")
        return summary

    settings = get_settings()
    # Stage N+1 cache: resolve each distinct bank_code's passwords ONCE
    # (Fernet decryption is otherwise repeated per attachment). Cache holds the
    # resolved password tuple on success, or the DecryptError on failure so the
    # bank's attachments can be skipped consistently without re-resolving.
    password_cache: dict[str, tuple[str, ...] | DecryptError] = {}
    for bank_code in {a.bank_code for a in attachments}:
        try:
            password_cache[bank_code] = await resolve_passwords(
                session, settings, bank_code
            )
        except DecryptError as exc:
            password_cache[bank_code] = exc

    processed = 0
    for attachment in attachments:
        try:
            cached = password_cache[attachment.bank_code]
            if isinstance(cached, DecryptError):
                # Pre-resolution failed for this bank: record the failure once
                # per attachment and skip decryption (no double-counting — the
                # per-item path is never entered for this attachment).
                error_msg = (
                    f"密碼解析失敗 ({attachment.bank_code}/"
                    f"{attachment.original_filename}): {cached}"
                )
                summary.failed_count += 1
                summary.errors.append(error_msg)
                logger.error(error_msg)
                await update_attachment_status(
                    session,
                    attachment,
                    status=StagedAttachmentStatus.DECRYPT_FAILED,
                    error_reason=str(cached),
                )
            else:
                await _process_attachment(attachment, session, summary, cached)
            # Per-item commit: a mid-batch crash must not lose already-processed
            # rows (and must not desync disk vs DB).
            await session.commit()
        except Exception:
            # Roll back only this item's uncommitted changes, then continue to
            # the next attachment (item B: partial success persists).
            await session.rollback()
            logger.exception(
                "decrypt item failed unexpectedly (%s/%s); rolled back, continuing",
                attachment.bank_code,
                attachment.original_filename,
            )
        finally:
            processed += 1
            await reporter.stage_item_done("decrypt", processed=processed)

    logger.info(
        "Decryption 完成：%d 解密, %d 透通, %d 略過, %d 失敗",
        summary.decrypted_count,
        summary.passthrough_count,
        summary.skipped_count,
        summary.failed_count,
    )

    return summary
