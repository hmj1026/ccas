"""批次分類 job 入口模組。

提供 run_classify_job() 與 run_reclassify_job()，
分別處理新交易分類與既有交易重跑分類。
"""

import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from ccas.classifier.engine import classify
from ccas.classifier.rules import load_rules
from ccas.classifier.staging import (
    fetch_all_transactions,
    fetch_unclassified_transactions,
    update_transaction_category,
)
from ccas.pipeline.progress import NoopProgressReporter, ProgressReporter

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClassifySummary:
    """分類批次的統計摘要。

    Attributes:
        classified_count: 成功分類的交易數量。
        skipped_count: 因已有分類而略過的數量。
        total_count: 處理的交易總數。
    """

    classified_count: int
    skipped_count: int
    total_count: int


async def run_classify_job(
    session: AsyncSession,
    reporter: ProgressReporter | None = None,
) -> ClassifySummary:
    """對所有未分類交易執行關鍵字分類。

    流程：
    1. 從 categories 資料表載入分類規則
    2. 查詢所有 category 為 NULL 的交易
    3. 逐筆以分類引擎判定分類後寫入
    4. 回傳統計摘要

    Args:
        session: 非同步 DB Session（由呼叫端注入）。
        reporter: 進度回報（pipeline-operations-center §3A.4）。``None``
            時走 NoopProgressReporter。

    Returns:
        ClassifySummary 統計摘要。
    """
    if reporter is None:
        reporter = NoopProgressReporter()

    rule_set = await load_rules(session)

    transactions = await fetch_unclassified_transactions(session)
    await reporter.stage_started("classify", total=len(transactions))
    if not transactions:
        logger.info("沒有未分類的交易，跳過分類")
        return ClassifySummary(classified_count=0, skipped_count=0, total_count=0)

    classified_count = 0
    processed = 0
    for txn in transactions:
        try:
            category = classify(txn.merchant, rule_set)
            await update_transaction_category(session, txn.id, category)
            classified_count += 1
        finally:
            processed += 1
            await reporter.stage_item_done("classify", processed=processed)

    await session.commit()

    logger.info("分類完成：%d 筆交易已分類", classified_count)
    return ClassifySummary(
        classified_count=classified_count,
        skipped_count=0,
        total_count=len(transactions),
    )


async def run_reclassify_job(session: AsyncSession) -> ClassifySummary:
    """對所有交易重跑分類。

    重新載入最新規則後，逐筆重新計算分類。
    只更新 category 欄位，不改寫原始交易資料。

    Args:
        session: 非同步 DB Session（由呼叫端注入）。

    Returns:
        ClassifySummary 統計摘要。
    """
    rule_set = await load_rules(session)

    transactions = await fetch_all_transactions(session)
    if not transactions:
        logger.info("沒有任何交易，跳過重跑分類")
        return ClassifySummary(classified_count=0, skipped_count=0, total_count=0)

    classified_count = 0
    skipped_count = 0
    for txn in transactions:
        new_category = classify(txn.merchant, rule_set)
        if txn.category == new_category:
            skipped_count += 1
            continue
        await update_transaction_category(session, txn.id, new_category)
        classified_count += 1

    await session.commit()

    logger.info(
        "重跑分類完成：%d 筆更新, %d 筆未變動",
        classified_count,
        skipped_count,
    )
    return ClassifySummary(
        classified_count=classified_count,
        skipped_count=skipped_count,
        total_count=len(transactions),
    )
