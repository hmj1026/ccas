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
from ccas.storage.models import StagedAttachment

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
    *,
    force: bool = False,
) -> None:
    """處理單一附件的解析。"""
    bank_code = attachment.bank_code
    staged_path = attachment.staged_path

    if staged_path is None:
        error_msg = f"缺少 staged_path，無法解析：bank_code={bank_code}"
        summary.failed_count += 1
        summary.errors.append(error_msg)
        logger.error(error_msg)
        await update_attachment_status(
            session, attachment, status="parse_failed", error_reason=error_msg
        )
        return

    # 取得銀行設定以獲取 active_parser_version
    bank_config = await get_bank_config(session, bank_code)
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
            session, attachment, status="parse_failed", error_reason=error_msg
        )
        return

    # 在 thread 中執行同步 parse 邏輯
    pdf_path = Path(staged_path)
    success, parse_result, error_detail = await asyncio.to_thread(
        _try_parse, candidates, pdf_path
    )

    if not success:
        pdf_filename = attachment.original_filename or "unknown"
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
            session, attachment, status="parse_failed", error_reason=error_detail
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
        await update_attachment_status(session, attachment, status="parsed")
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
    await create_bill_and_transactions(session, parse_result, file_path=staged_path)
    await update_attachment_status(session, attachment, status="parsed")

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
    summary = ParseSummary()
    force = options.force if options else False

    attachments = await fetch_parseable_attachments(session, options)
    if not attachments:
        logger.info("沒有待解析的附件，跳過 parsing")
        return summary

    for attachment in attachments:
        await _process_attachment(attachment, session, summary, force=force)

    await session.commit()

    logger.info(
        "Parsing 完成：%d 解析, %d 略過, %d 失敗",
        summary.parsed_count,
        summary.skipped_count,
        summary.failed_count,
    )

    return summary
