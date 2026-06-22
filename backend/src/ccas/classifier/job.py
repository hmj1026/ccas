"""批次分類 job 入口模組。

提供 run_classify_job() 與 run_reclassify_job()，
分別處理新交易分類與既有交易重跑分類。
"""

import logging
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import set_committed_value

from ccas.classifier.engine import DEFAULT_CATEGORY, classify
from ccas.classifier.rules import load_rules
from ccas.classifier.staging import (
    fetch_all_transactions,
    fetch_unclassified_transactions,
)
from ccas.classifier.user_rules import UserRuleMatcher
from ccas.errors import ClassifyError
from ccas.shared.progress import NoopProgressReporter, ProgressReporter
from ccas.storage.models import Transaction

logger = logging.getLogger(__name__)


async def _flush_category_updates(
    session: AsyncSession,
    pending: dict[str, list[Transaction]],
) -> None:
    """Apply accumulated category assignments as one UPDATE per category.

    Batching turns N per-row UPDATEs into K statements (K = distinct
    categories). ``synchronize_session=False`` skips identity-map
    synchronization, so the loaded instances are patched manually via
    ``set_committed_value`` — it updates the loaded value without marking
    the instance dirty (no per-row UPDATE re-emitted at flush) — keeping
    same-session reads of ``txn.category`` consistent with the DB.
    """
    for category, txns in pending.items():
        stmt = (
            update(Transaction)
            .where(Transaction.id.in_([txn.id for txn in txns]))
            .values(category=category)
            .execution_options(synchronize_session=False)
        )
        await session.execute(stmt)
        for txn in txns:
            set_committed_value(txn, "category", category)


async def _flush_commit_or_rollback(
    session: AsyncSession,
    pending: dict[str, list[Transaction]],
) -> None:
    """Flush accumulated category updates and commit, rolling back on failure.

    The batch is all-or-nothing: any flush/commit error rolls the whole batch
    back and raises ``ClassifyError`` so the pipeline stage is marked failed
    instead of leaving a polluted session for the downstream notify stage. The
    number of affected (un-written) transactions is logged for diagnosis.
    """
    if not pending:
        # Nothing changed (e.g. all rows manual_override / already correct);
        # skip the no-op commit so a commit error can't misreport 0 rows.
        return
    try:
        await _flush_category_updates(session, pending)
        await session.commit()
    except Exception as exc:
        affected = sum(len(txns) for txns in pending.values())
        logger.error(
            "classify flush 失敗，%d 筆交易分類結果未寫入，將 rollback",
            affected,
            exc_info=True,
        )
        await session.rollback()
        raise ClassifyError("分類結果寫入失敗", reason="flush/commit error") from exc


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

    # Accumulate {category: [transactions]} so writes collapse into one UPDATE
    # per distinct category instead of one per row.
    pending_updates: defaultdict[str, list[Transaction]] = defaultdict(list)

    for txn in transactions:
        try:
            # bills-management-and-insights §2.4 優先序：
            # manual_override → user_rules → 既有 engine → 預設
            if txn.manual_category_override:
                manual_override_count += 1
                continue

            user_category = await user_matcher.match(txn.merchant)
            if user_category is not None:
                pending_updates[user_category].append(txn)
                user_rule_hits += 1
                continue

            category = classify(txn.merchant, rule_set)
            pending_updates[category].append(txn)
            if category == DEFAULT_CATEGORY:
                unclassified += 1
            else:
                engine_hits += 1
        finally:
            processed += 1
            # Progress reporting is pure UI and non-business-critical: a reporter
            # failure (e.g. SQLite busy) must not abort the classify batch or
            # truncate it mid-loop. Swallow-with-log, consistent with the
            # ingest/decrypt/parse/bot stages.
            try:
                await reporter.stage_item_done("classify", processed=processed)
            except Exception:
                logger.warning(
                    "classify progress reporting failed (processed=%d); continuing",
                    processed,
                    exc_info=True,
                )

    await _flush_commit_or_rollback(session, pending_updates)

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
    # Accumulate {category: [transactions]} so writes collapse into one UPDATE
    # per distinct category instead of one per row.
    pending_updates: defaultdict[str, list[Transaction]] = defaultdict(list)
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
        pending_updates[new_category].append(txn)
        classified_count += 1

    await _flush_commit_or_rollback(session, pending_updates)

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
