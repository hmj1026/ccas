"""Gmail ingestion job 入口模組。

提供 run_ingestion_job() 作為單次批次處理入口，
逐一處理啟用中的銀行設定，下載 PDF 附件到 staging 區。
單筆失敗不會中止整個 batch。
"""

import asyncio
import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.config import get_settings
from ccas.ingestor.auth import load_credentials
from ccas.ingestor.gmail_client import (
    GmailAttachmentMeta,
    build_gmail_service,
    download_attachment,
    search_messages,
)
from ccas.ingestor.staging import (
    build_staged_path,
    create_staged_record,
    find_existing_staged,
)
from ccas.storage.models import BankConfig

logger = logging.getLogger(__name__)


@dataclass
class IngestionSummary:
    """單次 ingestion batch 的統計摘要。

    Attributes:
        banks_processed: 已處理的銀行數。
        messages_found: 搜尋到的候選郵件數。
        staged_count: 成功 staged 的附件數。
        skipped_count: 因 dedupe 略過的附件數。
        failed_count: 處理失敗的附件數。
        errors: 錯誤訊息清單。
    """

    banks_processed: int = 0
    messages_found: int = 0
    staged_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    errors: list[str] = field(default_factory=list)


async def _fetch_active_banks(session: AsyncSession) -> list[BankConfig]:
    """查詢所有啟用中且具有有效 gmail_filter 的銀行設定。"""
    stmt = select(BankConfig).where(
        BankConfig.is_active == True,  # noqa: E712
        BankConfig.gmail_filter != "",
        BankConfig.gmail_filter.is_not(None),
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def _process_attachment(
    session: AsyncSession,
    service,
    bank_code: str,
    attachment: GmailAttachmentMeta,
    staging_dir: str,
    summary: IngestionSummary,
) -> None:
    """處理單個 PDF 附件：dedupe 檢查、下載、寫檔、建立記錄。"""
    existing = await find_existing_staged(
        session, attachment.message_id, attachment.attachment_id
    )
    if existing is not None:
        summary.skipped_count += 1
        logger.debug(
            "略過已存在的附件：%s/%s",
            attachment.message_id,
            attachment.attachment_id,
        )
        return

    staged_path = build_staged_path(
        staging_dir, bank_code, attachment.message_id, attachment.filename
    )

    try:
        pdf_bytes = await asyncio.to_thread(
            download_attachment,
            service,
            attachment.message_id,
            attachment.attachment_id,
        )

        target_dir = staged_path.parent
        await asyncio.to_thread(
            lambda: target_dir.mkdir(parents=True, exist_ok=True)
        )
        await asyncio.to_thread(staged_path.write_bytes, pdf_bytes)

        await create_staged_record(
            session,
            bank_code=bank_code,
            message_id=attachment.message_id,
            attachment_id=attachment.attachment_id,
            message_date=attachment.message_date,
            original_filename=attachment.filename,
            staged_path=str(staged_path),
            status="staged",
        )
        summary.staged_count += 1
        logger.info(
            "已 staged 附件：%s -> %s", attachment.filename, staged_path
        )

    except Exception as exc:
        error_msg = f"附件下載失敗 ({bank_code}/{attachment.filename}): {exc}"
        summary.failed_count += 1
        summary.errors.append(error_msg)
        logger.error(error_msg)

        await create_staged_record(
            session,
            bank_code=bank_code,
            message_id=attachment.message_id,
            attachment_id=attachment.attachment_id,
            message_date=attachment.message_date,
            original_filename=attachment.filename,
            staged_path=None,
            status="failed",
            error_reason=str(exc),
        )


async def run_ingestion_job(session: AsyncSession) -> IngestionSummary:
    """執行單次 Gmail ingestion batch。

    流程：
    1. 載入 Gmail OAuth 憑證並建立 API service
    2. 查詢所有啟用中且具有 gmail_filter 的 BankConfig
    3. 對每家銀行搜尋候選郵件並處理 PDF 附件
    4. 回傳統計摘要

    Args:
        session: 非同步 DB Session（由呼叫端注入）。

    Returns:
        IngestionSummary 統計摘要。

    Raises:
        GmailAuthError: Gmail 驗證失敗時拋出（整個 job 無法繼續）。
    """
    settings = get_settings()
    summary = IngestionSummary()

    credentials = load_credentials(
        settings.gmail_credentials_path, settings.gmail_token_path
    )
    service = build_gmail_service(credentials)

    active_banks = await _fetch_active_banks(session)
    if not active_banks:
        logger.info("沒有啟用中的銀行設定，跳過 ingestion")
        return summary

    for bank in active_banks:
        summary.banks_processed += 1

        try:
            messages = await asyncio.to_thread(
                search_messages, service, bank.gmail_filter
            )
        except Exception as exc:
            error_msg = f"銀行 {bank.bank_code} Gmail 搜尋失敗: {exc}"
            summary.errors.append(error_msg)
            logger.error(error_msg)
            continue

        summary.messages_found += len(messages)

        for message in messages:
            for attachment in message.pdf_attachments:
                await _process_attachment(
                    session,
                    service,
                    bank.bank_code,
                    attachment,
                    settings.staging_dir,
                    summary,
                )

    await session.commit()

    logger.info(
        "Ingestion 完成：%d 銀行, %d 郵件, %d staged, %d skipped, %d failed",
        summary.banks_processed,
        summary.messages_found,
        summary.staged_count,
        summary.skipped_count,
        summary.failed_count,
    )

    return summary
