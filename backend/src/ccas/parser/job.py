"""批次 PDF 解析 job 入口模組。

提供 run_parse_job() 作為批次處理入口，
逐一處理所有狀態為 decrypted 的附件。
單筆失敗不會中止整個 batch。

核心邏輯已移至 ``ccas.parser.intake``（可注入 ports 的 ``ParserIntake``）；
本模組僅保留薄殼委派，維持既有公開介面。
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from ccas.parser.intake import ParseSummary, build_parser_intake
from ccas.shared.pipeline_types import PipelineOptions
from ccas.shared.progress import ProgressReporter

logger = logging.getLogger(__name__)

__all__ = ["ParseSummary", "run_parse_job"]


async def run_parse_job(
    session: AsyncSession,
    options: PipelineOptions | None = None,
    reporter: ProgressReporter | None = None,
) -> ParseSummary:
    """執行單次批次 PDF 解析。

    Args:
        session: 非同步 DB Session（由呼叫端注入）。
        options: Pipeline 執行參數（可選）。

    Returns:
        ParseSummary 統計摘要。
    """
    return await build_parser_intake().run(session, options=options, reporter=reporter)
