"""批次分類 job 入口模組。

提供 run_classify_job() 與 run_reclassify_job()，
分別處理新交易分類與既有交易重跑分類。
"""

import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from ccas.classifier.engine import DEFAULT_CATEGORY, classify
from ccas.classifier.rules import load_rules
from ccas.classifier.staging import (
    fetch_all_transactions,
    fetch_unclassified_transactions,
    update_transaction_category,
)
from ccas.classifier.user_rules import UserRuleMatcher
from ccas.pipeline.progress import NoopProgressReporter, ProgressReporter

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClassifySummary:
    """分類批次的統計摘要（bills-management-and-insights §2.6）。

    Attributes:
        classified_count: 成功分類的交易數量（user_rule_hits + engine_hits）。
        skipped_count: 因 manual_category_override 而略過的數量。
        total_count: 處理的交易總數。
        manual_override_count: manual_category_override=true 的略過數
            （與 skipped_count 相同，便於 stage_summary 顯示）。
        user_rule_hits: 由 UserRuleMatcher 命中的數量。
        engine_hits: 由內建 keyword engine 命中的數量。
        unclassified: 全部規則皆未命中、落到 ``DEFAULT_CATEGORY`` 的數量。
    """

    classified_count: int
    skipped_count: int
    total_count: int
    manual_override_count: int = 0
    user_rule_hits: int = 0
    engine_hits: int = 0
    unclassified: int = 0


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

    user_matcher = await UserRuleMatcher.load(session)
    rule_set = await load_rules(session)

    transactions = await fetch_unclassified_transactions(session)
    await reporter.stage_started("classify", total=len(transactions))
    if not transactions:
        logger.info("沒有未分類的交易，跳過分類")
        return ClassifySummary(classified_count=0, skipped_count=0, total_count=0)

    manual_override_count = 0
    user_rule_hits = 0
    engine_hits = 0
    unclassified = 0
    processed = 0

    for txn in transactions:
        try:
            # bills-management-and-insights §2.4 優先序：
            # manual_override → user_rules → 既有 engine → 預設
            if txn.manual_category_override:
                manual_override_count += 1
                continue

            user_category = await user_matcher.match(txn.merchant)
            if user_category is not None:
                await update_transaction_category(session, txn.id, user_category)
                user_rule_hits += 1
                continue

            category = classify(txn.merchant, rule_set)
            await update_transaction_category(session, txn.id, category)
            if category == DEFAULT_CATEGORY:
                unclassified += 1
            else:
                engine_hits += 1
        finally:
            processed += 1
            await reporter.stage_item_done("classify", processed=processed)

    await session.commit()

    # 與既有契約相容：classified_count 含所有寫入 category 的 row（即使是
    # DEFAULT_CATEGORY 也算，與 manual_override 的 skip 區分）
    classified_count = user_rule_hits + engine_hits + unclassified
    logger.info(
        "classify done: manual=%d user=%d engine=%d unclassified=%d total=%d",
        manual_override_count,
        user_rule_hits,
        engine_hits,
        unclassified,
        len(transactions),
    )
    return ClassifySummary(
        classified_count=classified_count,
        skipped_count=manual_override_count,
        total_count=len(transactions),
        manual_override_count=manual_override_count,
        user_rule_hits=user_rule_hits,
        engine_hits=engine_hits,
        unclassified=unclassified,
    )


async def run_reclassify_job(session: AsyncSession) -> ClassifySummary:
    """對所有交易重跑分類（bills-management-and-insights §2.4 優先序）。

    重新載入最新規則後，逐筆依 ``manual_override → user_rules → engine`` 順序重算。
    ``manual_category_override = true`` 的交易一律跳過，保留使用者編輯結果
    （§15.1：「手動改 category → 重跑 pipeline 5 次 → category 不變」）。

    Args:
        session: 非同步 DB Session（由呼叫端注入）。

    Returns:
        ClassifySummary 統計摘要；``skipped_count`` / ``manual_override_count``
        會包含被 manual_override 跳過的交易數。
    """
    user_matcher = await UserRuleMatcher.load(session)
    rule_set = await load_rules(session)

    transactions = await fetch_all_transactions(session)
    if not transactions:
        logger.info("沒有任何交易，跳過重跑分類")
        return ClassifySummary(classified_count=0, skipped_count=0, total_count=0)

    classified_count = 0
    skipped_count = 0
    manual_override_count = 0
    for txn in transactions:
        if txn.manual_category_override:
            manual_override_count += 1
            skipped_count += 1
            continue

        user_category = await user_matcher.match(txn.merchant)
        new_category = (
            user_category
            if user_category is not None
            else classify(txn.merchant, rule_set)
        )
        if txn.category == new_category:
            skipped_count += 1
            continue
        await update_transaction_category(session, txn.id, new_category)
        classified_count += 1

    await session.commit()

    logger.info(
        "重跑分類完成：%d 筆更新, %d 筆未變動（含 %d 筆 manual_override 跳過）",
        classified_count,
        skipped_count,
        manual_override_count,
    )
    return ClassifySummary(
        classified_count=classified_count,
        skipped_count=skipped_count,
        total_count=len(transactions),
        manual_override_count=manual_override_count,
    )
