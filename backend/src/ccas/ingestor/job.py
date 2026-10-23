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
from ccas.ingestor.credentials import resolve_bank_credential
from ccas.ingestor.filters import should_skip_attachment
from ccas.ingestor.gmail_client import (
    GmailAttachmentMeta,
    GmailMessage,
    build_gmail_service,
    download_attachment,
    search_messages,
)
from ccas.ingestor.lifecycle import (
    FetchExpiredError,
    StagedSource,
    StagingDisposition,
    StagingResult,
    StagingRollbackError,
    stage_source,
)
from ccas.shared.pipeline_types import PipelineOptions
from ccas.shared.progress import NoopProgressReporter, ProgressReporter
from ccas.storage.models import BankConfig, BankSettings

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


async def _apply_bank_settings_filter(
    session: AsyncSession, configs: list[BankConfig]
) -> list[BankConfig]:
    """Drop configs whose ``bank_settings.enabled`` was explicitly set to False.

    DB row precedence (oauth-onboarding-ui §4.4):
    ``bank_settings.enabled`` (if present) > ``bank_configs.is_active`` (already
    filtered upstream by base SQL) > default True.

    Implemented as a post-filter to avoid touching the existing SQL query that
    also enforces ``gmail_filter != ""``.
    """
    if not configs:
        return configs
    codes = [c.bank_code for c in configs]
    rows = await session.execute(
        select(BankSettings).where(BankSettings.code.in_(codes))
    )
    overrides = {r.code: r.enabled for r in rows.scalars().all()}
    return [c for c in configs if overrides.get(c.bank_code, True)]


async def _fetch_active_banks(
    session: AsyncSession,
    options: PipelineOptions | None = None,
) -> list[BankConfig]:
    """查詢所有啟用中且具有有效 gmail_filter 的銀行設定。

    若 options.bank_code 有值，僅回傳該銀行。

    對 ``bank_settings.enabled = false`` 的條目，於後處理層過濾掉
    （oauth-onboarding-ui §4.4 DB 優先 fallback 鏈）。
    """
    stmt = select(BankConfig).where(
        BankConfig.is_active == True,  # noqa: E712
        BankConfig.gmail_filter != "",
        BankConfig.gmail_filter.is_not(None),
    )
    if options and options.bank_code:
        stmt = stmt.where(BankConfig.bank_code == options.bank_code)
    result = await session.execute(stmt)
    configs = list(result.scalars().all())
    return await _apply_bank_settings_filter(session, configs)


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


async def _process_attachment(
    session: AsyncSession,
    service,
    bank_code: str,
    attachment: GmailAttachmentMeta,
    staging_dir: str,
    *,
    force: bool = False,
) -> StagingResult:
    """Adapt one Gmail PDF attachment to the shared statement lifecycle."""
    if should_skip_attachment(bank_code, attachment.filename):
        logger.debug(
            "附件檔名命中黑名單，跳過：%s/%s",
            bank_code,
            attachment.filename,
        )
        return StagingResult(StagingDisposition.SKIPPED)

    source = StagedSource(
        bank_code=bank_code,
        message_id=attachment.message_id,
        part_id=attachment.part_id,
        attachment_id=attachment.attachment_id,
        message_date=attachment.message_date,
        original_filename=attachment.filename,
    )

    async def acquire_pdf() -> bytes:
        return await asyncio.to_thread(
            download_attachment,
            service,
            attachment.message_id,
            attachment.attachment_id,
        )

    return await stage_source(
        session,
        staging_dir,
        source,
        acquire_pdf,
        force=force,
    )


async def _process_web_fetch(
    session: AsyncSession,
    bank_code: str,
    message: GmailMessage,
    staging_dir: str,
    settings: Settings,
    *,
    force: bool = False,
) -> StagingResult | None:
    """Adapt one web-fetch message to the shared statement lifecycle.

    ``None`` means no registered fetcher or a source message that the fetcher
    does not accept. Credentials are resolved lazily inside the acquisition
    callback, after the lifecycle has confirmed that this item needs fetching.
    """
    from ccas.ingestor.fetcher import fetcher_registry

    fetcher = fetcher_registry.get(bank_code)
    if fetcher is None:
        return None

    html_body = message.html_body
    assert html_body is not None  # noqa: S101
    if not fetcher.can_fetch(html_body):
        return None

    synthetic_attachment_id = f"web_fetch_{message.message_id}"
    synthetic_part_id = f"web:{message.message_id}"
    staged_filename = f"{bank_code}_{message.message_id}.pdf"
    source = StagedSource(
        bank_code=bank_code,
        message_id=message.message_id,
        part_id=synthetic_part_id,
        attachment_id=synthetic_attachment_id,
        message_date=message.message_date,
        original_filename=staged_filename,
        source_type="web_fetch",
    )

    async def acquire_pdf() -> bytes:
        credentials = {
            "national_id": await resolve_bank_credential(
                session, settings, bank_code, "NATIONAL_ID"
            )
            or "",
            "roc_birthday": await resolve_bank_credential(
                session, settings, bank_code, "ROC_BIRTHDAY"
            )
            or "",
        }
        try:
            return await asyncio.to_thread(
                fetcher.fetch_pdf,
                html_body,
                credentials,
            )
        except Exception as error:
            if any(marker in str(error) for marker in _EXPIRED_FETCH_MARKERS):
                raise FetchExpiredError(
                    str(error),
                    error_reason=_EXPIRED_FETCH_REASON,
                ) from error
            raise

    return await stage_source(
        session,
        staging_dir,
        source,
        acquire_pdf,
        force=force,
    )


def _record_staging_result(
    summary: IngestionSummary,
    result: StagingResult | None,
) -> None:
    if result is None:
        return
    if result.disposition == StagingDisposition.STAGED:
        summary.staged_count += 1
    elif result.disposition == StagingDisposition.SKIPPED:
        summary.skipped_count += 1
    else:
        summary.failed_count += 1
        if result.error_message:
            summary.errors.append(result.error_message)


async def run_ingestion_job(
    session: AsyncSession,
    options: PipelineOptions | None = None,
    reporter: ProgressReporter | None = None,
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
        reporter: 進度回報（pipeline-operations-center §3A.1）。``None`` 時走
            NoopProgressReporter。Ingest 為三層 nested loop（bank → message
            → attachment），Gmail 搜尋發生在外層 loop 內、無法在進入前
            pre-flatten。採 spec D11 「per-bank reset」方案：每銀行 Gmail
            搜尋完成後 emit 一次 ``stage_started("ingest", total=bank_total)``
            重置 processed 與 total，前端容忍跨 bank 的 total 變動。

    Returns:
        IngestionSummary 統計摘要。

    Raises:
        GmailAuthError: Gmail 驗證失敗時拋出（整個 job 無法繼續）。
    """
    if reporter is None:
        reporter = NoopProgressReporter()

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
        await reporter.stage_started("ingest", total=0)
        return summary

    force = options.force if options else False
    # Copy every ORM-backed config value before item commits/rollbacks can
    # expire BankConfig instances. Later banks must remain processable after
    # an earlier item's transaction fails.
    bank_sources = tuple((bank.bank_code, bank.gmail_filter) for bank in active_banks)

    for bank_code, gmail_filter in bank_sources:
        summary.banks_processed += 1

        gmail_query = _build_gmail_query(gmail_filter, options)

        try:
            # summary.errors is mutated inside the worker thread; safe because
            # the per-bank loop is sequential and we await this call (no other
            # coroutine touches summary.errors during the thread's window).
            messages = await asyncio.to_thread(
                search_messages,
                service,
                gmail_query,
                bank_code=bank_code,
                partial_errors=summary.errors,
            )
        except Exception as exc:
            error_msg = f"銀行 {bank_code} Gmail 搜尋失敗: {exc}"
            summary.errors.append(error_msg)
            logger.error(error_msg, exc_info=True)
            continue

        summary.messages_found += len(messages)

        # Per-bank flatten: count items the inner loop will actually process.
        bank_total = sum(
            len(msg.pdf_attachments)
            if msg.pdf_attachments
            else (1 if msg.html_body is not None else 0)
            for msg in messages
        )
        await reporter.stage_started("ingest", total=bank_total)
        bank_processed = 0

        for message in messages:
            if message.pdf_attachments:
                for attachment in message.pdf_attachments:
                    try:
                        result = await _process_attachment(
                            session,
                            service,
                            bank_code,
                            attachment,
                            settings.staging_dir,
                            force=force,
                        )
                        _record_staging_result(summary, result)
                    except StagingRollbackError:
                        raise
                    except Exception as exc:
                        try:
                            await session.rollback()
                        except Exception as rollback_error:
                            logger.exception("ingest rollback failed")
                            raise StagingRollbackError(
                                "ingest item rollback failed"
                            ) from rollback_error
                        error_msg = (
                            f"附件處理失敗 ({bank_code}/{attachment.filename}): {exc}"
                        )
                        summary.failed_count += 1
                        summary.errors.append(error_msg)
                        logger.exception(
                            "ingest item failed unexpectedly (%s/%s); rolled "
                            "back, continuing",
                            bank_code,
                            attachment.filename,
                        )
                    finally:
                        bank_processed += 1
                        # Progress reporting is pure UI and non-business-
                        # critical: a reporter failure must not abort the loop
                        # or roll back the already-committed item. Swallow-with-
                        # log is deliberate here (logged, so not a silent
                        # failure).
                        try:
                            await reporter.stage_item_done(
                                "ingest", processed=bank_processed
                            )
                        except Exception:
                            logger.warning(
                                "ingest progress reporting failed "
                                "(processed=%d); continuing",
                                bank_processed,
                                exc_info=True,
                            )
            elif message.html_body is not None:
                try:
                    result = await _process_web_fetch(
                        session,
                        bank_code,
                        message,
                        settings.staging_dir,
                        settings,
                        force=force,
                    )
                    _record_staging_result(summary, result)
                except StagingRollbackError:
                    raise
                except Exception as exc:
                    try:
                        await session.rollback()
                    except Exception as rollback_error:
                        logger.exception("ingest rollback failed")
                        raise StagingRollbackError(
                            "ingest web-fetch rollback failed"
                        ) from rollback_error
                    error_msg = (
                        f"Web-fetch 處理失敗 ({bank_code}/{message.message_id}): {exc}"
                    )
                    summary.failed_count += 1
                    summary.errors.append(error_msg)
                    logger.exception(
                        "ingest web-fetch item failed unexpectedly (%s/%s); "
                        "rolled back, continuing",
                        bank_code,
                        message.message_id,
                    )
                finally:
                    bank_processed += 1
                    # Same rationale as above: progress reporting failures are
                    # logged but never abort the already-committed item.
                    try:
                        await reporter.stage_item_done(
                            "ingest", processed=bank_processed
                        )
                    except Exception:
                        logger.warning(
                            "ingest progress reporting failed "
                            "(processed=%d); continuing",
                            bank_processed,
                            exc_info=True,
                        )

    # Each source lifecycle owns its per-item commit; no batch transaction remains.
    logger.info(
        "Ingestion 完成：%d 銀行, %d 郵件, %d staged, %d skipped, %d failed",
        summary.banks_processed,
        summary.messages_found,
        summary.staged_count,
        summary.skipped_count,
        summary.failed_count,
    )

    return summary
