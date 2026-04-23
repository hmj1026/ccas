"""Gmail ingestion job 入口模組。

提供 run_ingestion_job() 作為單次批次處理入口，
逐一處理啟用中的銀行設定，下載 PDF 附件到 staging 區。
單筆失敗不會中止整個 batch。
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.config import Settings, get_settings
from ccas.ingestor.auth import load_credentials
from ccas.ingestor.filters import should_skip_attachment
from ccas.ingestor.gmail_client import (
    GmailAttachmentMeta,
    GmailMessage,
    build_gmail_service,
    download_attachment,
    search_messages,
)
from ccas.ingestor.staging import (
    backfill_part_id,
    build_staged_path,
    create_staged_record,
    delete_staged_record,
    find_existing_staged,
    resolve_staged_path,
    staged_path_for_storage,
    update_staged_record_failure,
)
from ccas.pipeline.options import PipelineOptions
from ccas.storage.models import BankConfig

logger = logging.getLogger(__name__)

# Error message fragments that map to status=fetch_expired instead of
# status=failed. `record_not_found` is raised by FUBON fetcher when the
# email's one-time serial_key has been consumed or aged out.
_EXPIRED_FETCH_MARKERS: tuple[str, ...] = ("record_not_found:",)
_EXPIRED_FETCH_REASON = (
    "fetch_expired: 下載連結已失效（serial_key 已被使用或超過有效期）"
)


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


async def _fetch_active_banks(
    session: AsyncSession,
    options: PipelineOptions | None = None,
) -> list[BankConfig]:
    """查詢所有啟用中且具有有效 gmail_filter 的銀行設定。

    若 options.bank_code 有值，僅回傳該銀行。
    """
    stmt = select(BankConfig).where(
        BankConfig.is_active == True,  # noqa: E712
        BankConfig.gmail_filter != "",
        BankConfig.gmail_filter.is_not(None),
    )
    if options and options.bank_code:
        stmt = stmt.where(BankConfig.bank_code == options.bank_code)
    result = await session.execute(stmt)
    return list(result.scalars().all())


def _build_gmail_query(
    base_filter: str,
    options: PipelineOptions | None,
) -> str:
    """組合銀行的 gmail_filter 與日期篩選子句。"""
    if not options:
        return base_filter
    date_clause = options.gmail_date_filter()
    if not date_clause:
        return base_filter
    return f"{base_filter} {date_clause}"


async def _cleanup_old_staged_file(staging_dir: str, staged_path: str | None) -> None:
    """刪除舊的 staging 檔案（若存在）。"""
    if not staged_path:
        return
    try:
        path = resolve_staged_path(staging_dir, staged_path)
    except ValueError:
        logger.warning("staged_path 逃逸 staging 根目錄，跳過刪除：%s", staged_path)
        return
    if path.exists():
        await asyncio.to_thread(path.unlink)
        logger.debug("已刪除舊 staging 檔案：%s", staged_path)


async def _process_attachment(
    session: AsyncSession,
    service,
    bank_code: str,
    attachment: GmailAttachmentMeta,
    staging_dir: str,
    summary: IngestionSummary,
    *,
    force: bool = False,
) -> None:
    """處理單個 PDF 附件：dedupe 檢查、下載、寫檔、建立記錄。"""
    if should_skip_attachment(bank_code, attachment.filename):
        summary.skipped_count += 1
        logger.debug(
            "附件檔名命中黑名單，跳過：%s/%s",
            bank_code,
            attachment.filename,
        )
        return

    existing = await find_existing_staged(
        session,
        attachment.message_id,
        attachment.part_id,
        attachment.filename,
    )
    if existing is not None:
        is_failed_retry = existing.status == "failed"
        if not force and not is_failed_retry:
            # Opportunistic backfill: if the legacy row lacks gmail_part_id
            # (pre-migration data matched via filename fallback), write it in
            # now so future lookups use the primary key path.
            await backfill_part_id(session, existing, attachment.part_id)
            summary.skipped_count += 1
            logger.debug(
                "略過已存在的附件：%s/%s",
                attachment.message_id,
                attachment.attachment_id,
            )
            return

        if is_failed_retry:
            logger.info(
                "自動重試 failed 附件：%s/%s",
                attachment.message_id,
                attachment.attachment_id,
            )
        else:
            # Force mode: defer cleanup until download succeeds
            logger.info(
                "Force 模式：重新下載 %s/%s",
                attachment.message_id,
                attachment.attachment_id,
            )

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
        await asyncio.to_thread(lambda: target_dir.mkdir(parents=True, exist_ok=True))
        await asyncio.to_thread(staged_path.write_bytes, pdf_bytes)

        # Cleanup old record only after new download succeeds
        new_stored = staged_path_for_storage(staging_dir, staged_path)
        if existing is not None:
            if existing.staged_path is not None and existing.staged_path != new_stored:
                await _cleanup_old_staged_file(staging_dir, existing.staged_path)
            await delete_staged_record(session, existing)

        await create_staged_record(
            session,
            bank_code=bank_code,
            message_id=attachment.message_id,
            attachment_id=attachment.attachment_id,
            message_date=attachment.message_date,
            original_filename=attachment.filename,
            staged_path=new_stored,
            status="staged",
            part_id=attachment.part_id,
        )
        summary.staged_count += 1
        logger.info("已 staged 附件：%s -> %s", attachment.filename, staged_path)

    except Exception as exc:
        error_msg = f"附件下載失敗 ({bank_code}/{attachment.filename}): {exc}"
        summary.failed_count += 1
        summary.errors.append(error_msg)
        logger.error(error_msg, exc_info=True)

        # In force mode, preserve the existing good record
        if existing is None:
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
                part_id=attachment.part_id,
            )


async def _process_web_fetch(
    session: AsyncSession,
    bank_code: str,
    message: GmailMessage,
    staging_dir: str,
    settings: Settings,
    summary: IngestionSummary,
    *,
    force: bool = False,
) -> None:
    """處理無附件郵件的 web-fetch PDF 下載。

    透過 FetcherRegistry 查找對應的 BankFetcher，
    從 HTML 郵件內容中下載 PDF 帳單。
    """
    from ccas.ingestor.fetcher import fetcher_registry

    fetcher = fetcher_registry.get(bank_code)
    if fetcher is None:
        return

    assert message.html_body is not None  # noqa: S101
    if not fetcher.can_fetch(message.html_body):
        return

    synthetic_attachment_id = f"web_fetch_{message.message_id}"
    synthetic_part_id = f"web:{message.message_id}"
    staged_filename = f"{bank_code}_{message.message_id}.pdf"

    existing = await find_existing_staged(
        session,
        message.message_id,
        synthetic_part_id,
        staged_filename,
    )
    if existing is not None:
        is_failed_retry = existing.status == "failed"
        if not force and not is_failed_retry:
            await backfill_part_id(session, existing, synthetic_part_id)
            summary.skipped_count += 1
            logger.debug("略過已存在的 web-fetch：%s", message.message_id)
            return

        if is_failed_retry:
            logger.info("自動重試 failed web-fetch：%s", message.message_id)
        else:
            logger.info("Force 模式：重新 web-fetch %s", message.message_id)

    credentials = {
        "national_id": settings.get_bank_credential(bank_code, "NATIONAL_ID") or "",
        "roc_birthday": settings.get_bank_credential(bank_code, "ROC_BIRTHDAY") or "",
    }

    staged_path = build_staged_path(
        staging_dir, bank_code, message.message_id, staged_filename
    )

    try:
        pdf_bytes = await asyncio.to_thread(
            fetcher.fetch_pdf, message.html_body, credentials
        )

        target_dir = staged_path.parent
        await asyncio.to_thread(lambda: target_dir.mkdir(parents=True, exist_ok=True))
        await asyncio.to_thread(staged_path.write_bytes, pdf_bytes)

        new_stored = staged_path_for_storage(staging_dir, staged_path)
        if existing is not None:
            if existing.staged_path is not None and existing.staged_path != new_stored:
                await _cleanup_old_staged_file(staging_dir, existing.staged_path)
            await delete_staged_record(session, existing)

        await create_staged_record(
            session,
            bank_code=bank_code,
            message_id=message.message_id,
            attachment_id=synthetic_attachment_id,
            message_date=message.message_date,
            original_filename=staged_filename,
            staged_path=new_stored,
            status="staged",
            source_type="web_fetch",
            part_id=synthetic_part_id,
        )
        summary.staged_count += 1
        logger.info("已 web-fetch staged：%s -> %s", message.message_id, staged_path)

    except Exception as exc:
        exc_str = str(exc)
        is_expired = any(marker in exc_str for marker in _EXPIRED_FETCH_MARKERS)

        if is_expired:
            error_msg = (
                f"Web-fetch 略過（連結已失效）({bank_code}/{message.message_id}): {exc}"
            )
            summary.skipped_count += 1
            logger.warning(error_msg)
            new_status = "fetch_expired"
            new_reason = _EXPIRED_FETCH_REASON
        else:
            error_msg = f"Web-fetch 失敗 ({bank_code}/{message.message_id}): {exc}"
            summary.failed_count += 1
            summary.errors.append(error_msg)
            logger.error(error_msg, exc_info=True)
            new_status = "failed"
            new_reason = exc_str

        if existing is None:
            await create_staged_record(
                session,
                bank_code=bank_code,
                message_id=message.message_id,
                attachment_id=synthetic_attachment_id,
                message_date=message.message_date,
                original_filename=staged_filename,
                staged_path=None,
                status=new_status,
                error_reason=new_reason,
                source_type="web_fetch",
                part_id=synthetic_part_id,
            )
        else:
            await update_staged_record_failure(
                session,
                existing,
                status=new_status,
                error_reason=new_reason,
            )


async def run_ingestion_job(
    session: AsyncSession,
    options: PipelineOptions | None = None,
) -> IngestionSummary:
    """執行單次 Gmail ingestion batch。

    流程：
    1. 載入 Gmail OAuth 憑證並建立 API service
    2. 查詢所有啟用中且具有 gmail_filter 的 BankConfig
    3. 對每家銀行搜尋候選郵件並處理 PDF 附件
    4. 回傳統計摘要

    Args:
        session: 非同步 DB Session（由呼叫端注入）。
        options: Pipeline 執行參數（可選）。

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

    active_banks = await _fetch_active_banks(session, options)
    if not active_banks:
        msg = (
            "[Ingest] 未找到任何啟用的銀行設定。"
            "請先執行 python -m ccas.tools.bank_configs --apply 初始化銀行設定。"
        )
        logger.warning(msg)
        summary.errors.append(msg)
        return summary

    force = options.force if options else False

    for bank in active_banks:
        summary.banks_processed += 1

        gmail_query = _build_gmail_query(bank.gmail_filter, options)

        try:
            messages = await asyncio.to_thread(search_messages, service, gmail_query)
        except Exception as exc:
            error_msg = f"銀行 {bank.bank_code} Gmail 搜尋失敗: {exc}"
            summary.errors.append(error_msg)
            logger.error(error_msg)
            continue

        summary.messages_found += len(messages)

        for message in messages:
            if message.pdf_attachments:
                for attachment in message.pdf_attachments:
                    await _process_attachment(
                        session,
                        service,
                        bank.bank_code,
                        attachment,
                        settings.staging_dir,
                        summary,
                        force=force,
                    )
            elif message.html_body is not None:
                await _process_web_fetch(
                    session,
                    bank.bank_code,
                    message,
                    settings.staging_dir,
                    settings,
                    summary,
                    force=force,
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
