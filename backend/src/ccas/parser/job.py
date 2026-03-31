"""批次 PDF 解析 job 入口模組。

提供 run_parse_job() 作為批次處理入口，
逐一處理所有狀態為 decrypted 的附件。
單筆失敗不會中止整個 batch。
"""

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from ccas.parser.base import BankParser, ParseError
from ccas.parser.registry import ParserNotFoundError, registry
from ccas.parser.staging import (
    check_bill_exists,
    create_bill_and_transactions,
    fetch_parseable_attachments,
    get_bank_config,
    update_attachment_status,
)
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
    candidates: list[BankParser], pdf_path: Path
) -> tuple[bool, "ParseResult | None", str]:
    """依序嘗試候選 parser，回傳第一個成功的結果。

    Args:
        candidates: 排序後的候選 parser 列表。
        pdf_path: 已解密 PDF 的檔案路徑。

    Returns:
        (success, result, error_message) 三元組。
    """
    from ccas.parser.result import ParseResult

    errors: list[str] = []
    for parser in candidates:
        try:
            if not parser.can_parse(pdf_path):
                errors.append(
                    f"{parser.bank_code}/{parser.version}: can_parse=False"
                )
                continue
            result = parser.parse(pdf_path)
            return True, result, ""
        except ParseError as exc:
            errors.append(f"{parser.bank_code}/{parser.version}: {exc}")
        except Exception as exc:
            errors.append(
                f"{parser.bank_code}/{parser.version}: 非預期錯誤 {exc}"
            )

    return False, None, "; ".join(errors)


async def _process_attachment(
    attachment: StagedAttachment,
    session: AsyncSession,
    summary: ParseSummary,
) -> None:
    """處理單一附件的解析。"""
    bank_code = attachment.bank_code

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
    pdf_path = Path(attachment.staged_path)  # type: ignore[arg-type]
    success, parse_result, error_detail = await asyncio.to_thread(
        _try_parse, candidates, pdf_path
    )

    if not success:
        error_msg = (
            f"所有 parser 皆失敗 ({bank_code}/{attachment.original_filename}): "
            f"{error_detail}"
        )
        summary.failed_count += 1
        summary.errors.append(error_msg)
        logger.error(error_msg)
        await update_attachment_status(
            session, attachment, status="parse_failed", error_reason=error_detail
        )
        return

    assert parse_result is not None

    # 去重複：檢查同銀行同月份帳單是否已存在
    if await check_bill_exists(
        session, parse_result.bank_code, parse_result.billing_month
    ):
        summary.skipped_count += 1
        logger.info(
            "帳單已存在，略過：%s/%s",
            parse_result.bank_code,
            parse_result.billing_month,
        )
        await update_attachment_status(session, attachment, status="parsed")
        return

    # 建立 Bill 與 Transaction 記錄
    await create_bill_and_transactions(
        session, parse_result, file_path=attachment.staged_path
    )
    await update_attachment_status(session, attachment, status="parsed")

    summary.parsed_count += 1
    logger.info(
        "解析成功：%s/%s (%s)",
        bank_code,
        attachment.original_filename,
        parse_result.billing_month,
    )


async def run_parse_job(session: AsyncSession) -> ParseSummary:
    """執行單次批次 PDF 解析。

    流程：
    1. 查詢所有狀態為 decrypted 的附件
    2. 逐一嘗試解析，建立帳單與交易記錄
    3. 單筆失敗不中止整個批次
    4. 回傳統計摘要

    Args:
        session: 非同步 DB Session（由呼叫端注入）。

    Returns:
        ParseSummary 統計摘要。
    """
    summary = ParseSummary()

    attachments = await fetch_parseable_attachments(session)
    if not attachments:
        logger.info("沒有待解析的附件，跳過 parsing")
        return summary

    for attachment in attachments:
        await _process_attachment(attachment, session, summary)

    await session.commit()

    logger.info(
        "Parsing 完成：%d 解析, %d 略過, %d 失敗",
        summary.parsed_count,
        summary.skipped_count,
        summary.failed_count,
    )

    return summary
