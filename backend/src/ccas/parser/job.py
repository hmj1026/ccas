"""批次 PDF 解析 job 入口模組。

提供 run_parse_job() 作為批次處理入口，
逐一處理所有狀態為 decrypted 的附件。
單筆失敗不會中止整個 batch。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from ccas.config import get_settings
from ccas.ingestor.staging import resolve_staged_path
from ccas.parser.base import BankParser, ParseError
from ccas.parser.registry import ParserNotFoundError, registry
from ccas.parser.result import ParseResult
from ccas.parser.staging import (
    check_bill_exists,
    create_bill_and_transactions,
    delete_existing_bill,
    fetch_parseable_attachments,
    get_bank_config,
    update_attachment_status,
)
from ccas.pipeline.options import PipelineOptions
from ccas.pipeline.progress import NoopProgressReporter, ProgressReporter
from ccas.storage.models import BankConfig, StagedAttachment, StagedAttachmentStatus

logger = logging.getLogger(__name__)


@dataclass
class ParseSummary:
    """單次解析 batch 的統計摘要。

    Attributes:
        parsed_count: 成功解析並建立帳單的數量。
        skipped_count: 已完成解析或帳單已存在而略過的數量。
        failed_count: 解析失敗的數量。
        errors: 錯誤訊息清單。
    """

    parsed_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    errors: list[str] = field(default_factory=list)


def _try_parse(
    candidates: Sequence[BankParser], pdf_path: Path
) -> tuple[bool, ParseResult | None, str]:
    """依序嘗試候選 parser，回傳第一個成功的結果。

    Args:
        candidates: 排序後的候選 parser 列表。
        pdf_path: 已解密 PDF 的檔案路徑。

    Returns:
        (success, result, error_message) 三元組。
    """

    errors: list[str] = []
    pdf_filename = pdf_path.name
    for parser in candidates:
        try:
            logger.debug(
                "嘗試 parser %s/%s: %s",
                parser.bank_code,
                parser.version,
                pdf_filename,
            )
            if not parser.can_parse(pdf_path):
                logger.debug(
                    "parser %s/%s can_parse=False: %s",
                    parser.bank_code,
                    parser.version,
                    pdf_filename,
                )
                errors.append(f"{parser.bank_code}/{parser.version}: can_parse=False")
                continue
            result = parser.parse(pdf_path)
            logger.info(
                "parser 匹配成功: parser=%s/%s, bank_code=%s, pdf=%s",
                parser.bank_code,
                parser.version,
                parser.bank_code,
                pdf_filename,
            )
            return True, result, ""
        except ParseError as exc:
            logger.error(
                "parse 失敗: parser=%s/%s, pdf=%s, error_type=ParseError, detail=%s",
                parser.bank_code,
                parser.version,
                pdf_filename,
                str(exc),
                extra={
                    "pdf_filename": pdf_filename,
                    "bank_code": parser.bank_code,
                    "error_type": "ParseError",
                    "error_detail": str(exc),
                },
            )
            errors.append(f"{parser.bank_code}/{parser.version}: {exc}")
        except Exception as exc:
            logger.error(
                "parse 非預期錯誤: parser=%s/%s, pdf=%s, error_type=%s, detail=%s",
                parser.bank_code,
                parser.version,
                pdf_filename,
                type(exc).__name__,
                str(exc),
                exc_info=True,
                extra={
                    "pdf_filename": pdf_filename,
                    "bank_code": parser.bank_code,
                    "error_type": type(exc).__name__,
                    "error_detail": str(exc),
                },
            )
            errors.append(f"{parser.bank_code}/{parser.version}: 非預期錯誤 {exc}")

    logger.warning(
        "所有 parser 均無法匹配: pdf=%s, 嘗試過=%s",
        pdf_filename,
        ", ".join(f"{p.bank_code}/{p.version}" for p in candidates),
        extra={
            "pdf_filename": pdf_filename,
            "attempted_parsers": [f"{p.bank_code}/{p.version}" for p in candidates],
        },
    )
    return False, None, "; ".join(errors)


async def _process_attachment(
    attachment: StagedAttachment,
    session: AsyncSession,
    summary: ParseSummary,
    bank_config: BankConfig | None,
    *,
    force: bool = False,
) -> None:
    """處理單一附件的解析。

    ``bank_config`` 由呼叫端的 per-bank 快取預先載入後傳入（避免每筆附件
    重複查詢 ``bank_configs``）。``None`` 表示該銀行無設定。
    """
    bank_code = attachment.bank_code
    raw_path = attachment.staged_path

    if raw_path is None:
        error_msg = f"缺少 staged_path，無法解析：bank_code={bank_code}"
        summary.failed_count += 1
        summary.errors.append(error_msg)
        logger.error(error_msg)
        await update_attachment_status(
            session,
            attachment,
            status=StagedAttachmentStatus.PARSE_FAILED,
            error_reason=error_msg,
        )
        return

    settings = get_settings()
    try:
        staged_path = resolve_staged_path(settings.staging_dir, raw_path)
    except ValueError:
        error_msg = (
            f"staged_path 逃逸 staging 根目錄：bank_code={bank_code}, path={raw_path}"
        )
        summary.failed_count += 1
        summary.errors.append(error_msg)
        logger.error(error_msg)
        await update_attachment_status(
            session,
            attachment,
            status=StagedAttachmentStatus.PARSE_FAILED,
            error_reason=error_msg,
        )
        return

    # 銀行設定由呼叫端 per-bank 快取預先載入並傳入（active_parser_version）。
    active_version = bank_config.active_parser_version if bank_config else None

    # 從 registry 取得候選 parser
    try:
        candidates = registry.resolve(bank_code, active_version)
    except ParserNotFoundError:
        error_msg = f"找不到 parser：bank_code={bank_code}"
        summary.failed_count += 1
        summary.errors.append(error_msg)
        logger.error(error_msg)
        await update_attachment_status(
            session,
            attachment,
            status=StagedAttachmentStatus.PARSE_FAILED,
            error_reason=error_msg,
        )
        return

    # 在 thread 中執行同步 parse 邏輯，並以逾時隔離毒藥 PDF（單筆無限阻塞時，
    # event loop 不會被卡住）。注意：wait_for 逾時後背景 thread 仍會跑到
    # pdfplumber 自然返回（Python thread 無法強制中止），thread 會短暫洩漏，
    # 但 worker 可立即繼續處理下一筆——已達隔離目的。
    try:
        success, parse_result, error_detail = await asyncio.wait_for(
            asyncio.to_thread(_try_parse, candidates, staged_path),
            timeout=settings.pdf_parse_timeout_seconds,
        )
    except TimeoutError:
        pdf_filename = attachment.original_filename or "unknown"
        error_msg = (
            f"PDF 解析逾時 (>{settings.pdf_parse_timeout_seconds:.0f}s)，"
            f"疑似毒藥 PDF: {bank_code}/{pdf_filename}"
        )
        summary.failed_count += 1
        summary.errors.append(error_msg)
        logger.error(
            error_msg,
            extra={
                "pdf_filename": pdf_filename,
                "bank_code": bank_code,
                "error_type": "ParseTimeout",
            },
        )
        await update_attachment_status(
            session,
            attachment,
            status=StagedAttachmentStatus.PARSE_FAILED,
            error_reason=error_msg,
        )
        return

    if not success:
        pdf_filename = attachment.original_filename or "unknown"

        # Zero-balance historical bills (e.g. SINOPAC 2021 無消費帳單) raise a
        # ParseError tagged with "zero-balance" — treat as skip, not failure,
        # since there is no actionable amount / due_date to persist.
        if "zero-balance" in (error_detail or ""):
            summary.skipped_count += 1
            logger.info(
                "略過零額歷史帳單: bank_code=%s pdf=%s detail=%s",
                bank_code,
                pdf_filename,
                error_detail,
            )
            await update_attachment_status(
                session,
                attachment,
                status=StagedAttachmentStatus.PARSE_SKIPPED,
                error_reason=error_detail,
            )
            return

        error_msg = f"所有 parser 皆失敗 ({bank_code}/{pdf_filename}): {error_detail}"
        summary.failed_count += 1
        summary.errors.append(error_msg)
        logger.error(
            error_msg,
            extra={
                "pdf_filename": pdf_filename,
                "bank_code": bank_code,
                "error_type": "AllParsersFailed",
                "error_detail": error_detail,
            },
        )
        await update_attachment_status(
            session,
            attachment,
            status=StagedAttachmentStatus.PARSE_FAILED,
            error_reason=error_detail,
        )
        return

    assert parse_result is not None

    # 去重複：檢查同銀行同月份帳單是否已存在
    bill_exists = await check_bill_exists(
        session, parse_result.bank_code, parse_result.billing_month
    )
    if bill_exists and not force:
        summary.skipped_count += 1
        logger.info(
            "帳單已存在，略過：%s/%s",
            parse_result.bank_code,
            parse_result.billing_month,
        )
        await update_attachment_status(
            session, attachment, status=StagedAttachmentStatus.PARSED
        )
        return

    if bill_exists and force:
        logger.info(
            "Force 模式：刪除舊帳單並重新解析 %s/%s",
            parse_result.bank_code,
            parse_result.billing_month,
        )
        await delete_existing_bill(
            session, parse_result.bank_code, parse_result.billing_month
        )

    # 建立 Bill 與 Transaction 記錄
    await create_bill_and_transactions(
        session, parse_result, file_path=str(staged_path)
    )
    await update_attachment_status(
        session, attachment, status=StagedAttachmentStatus.PARSED
    )

    summary.parsed_count += 1
    logger.info(
        "解析成功：%s/%s (%s)",
        bank_code,
        attachment.original_filename,
        parse_result.billing_month,
    )


async def run_parse_job(
    session: AsyncSession,
    options: PipelineOptions | None = None,
    reporter: ProgressReporter | None = None,
) -> ParseSummary:
    """執行單次批次 PDF 解析。

    流程：
    1. 查詢所有狀態為 decrypted 的附件
    2. 逐一嘗試解析，建立帳單與交易記錄
    3. 單筆失敗不中止整個批次
    4. 回傳統計摘要

    Args:
        session: 非同步 DB Session（由呼叫端注入）。
        options: Pipeline 執行參數（可選）。

    Returns:
        ParseSummary 統計摘要。
    """
    if reporter is None:
        reporter = NoopProgressReporter()

    summary = ParseSummary()
    force = options.force if options else False

    attachments = await fetch_parseable_attachments(session, options)
    await reporter.stage_started("parse", total=len(attachments))
    if not attachments:
        logger.info("沒有待解析的附件，跳過 parsing")
        return summary

    # Stage N+1 cache: load each distinct bank_code's BankConfig ONCE instead of
    # querying bank_configs per attachment.
    bank_config_cache: dict[str, BankConfig | None] = {}
    for bank_code in {a.bank_code for a in attachments}:
        bank_config_cache[bank_code] = await get_bank_config(session, bank_code)

    processed = 0
    for attachment in attachments:
        try:
            await _process_attachment(
                attachment,
                session,
                summary,
                bank_config_cache.get(attachment.bank_code),
                force=force,
            )
            # Per-item commit: a mid-batch crash must not lose already-processed
            # rows (and must not desync disk vs DB).
            await session.commit()
        except Exception:
            # Roll back only this item's uncommitted changes, then continue to
            # the next attachment (item B: partial success persists).
            await session.rollback()
            logger.exception(
                "parse item failed unexpectedly (%s/%s); rolled back, continuing",
                attachment.bank_code,
                attachment.original_filename,
            )
        finally:
            processed += 1
            # Progress reporting is pure UI and non-business-critical: a
            # reporter failure must not abort the loop or roll back the
            # already-committed item. Swallow-with-log is deliberate here
            # (logged, so not a silent failure).
            try:
                await reporter.stage_item_done("parse", processed=processed)
            except Exception:
                logger.warning(
                    "parse progress reporting failed (processed=%d); continuing",
                    processed,
                    exc_info=True,
                )

    logger.info(
        "Parsing 完成：%d 解析, %d 略過, %d 失敗",
        summary.parsed_count,
        summary.skipped_count,
        summary.failed_count,
    )

    return summary
