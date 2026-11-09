"""批次分類 job 入口模組。

提供 run_classify_job() 與 run_reclassify_job()，
分別處理新交易分類與既有交易重跑分類。
"""

import logging
from collections import Counter, defaultdict
from dataclasses import dataclass

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import set_committed_value

from ccas.classifier.decision import Classifier, DecisionSource
from ccas.classifier.staging import (
    fetch_all_transactions,
    fetch_unclassified_transactions,
)
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
        classified_count: 寫入消費類別的交易數量（user_rule_hits + engine_hits +
            unclassified；重新分類時為實際變更的數量）。
        skipped_count: 未寫入的數量（手動分類覆寫；重新分類時另含未變動者）。
        total_count: 處理的交易總數。
        manual_override_count: 分類判定來源為 ``manual_override`` 的數量。
        user_rule_hits: 分類判定來源為 ``user_rule`` 的數量。
        engine_hits: 分類判定來源為 ``keyword`` 的數量。
        unclassified: 分類判定來源為 ``default``（預設消費類別）的數量。
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
    *,
    classifier: Classifier | None = None,
) -> ClassifySummary:
    """對所有未分類交易取得分類判定並寫入消費類別。

    流程：
    1. 載入分類判定（分類規則 + 關鍵字規則）
    2. 查詢所有 category 為 NULL 的交易
    3. 逐筆取得分類判定後批次寫入
    4. 回傳統計摘要

    Args:
        session: 非同步 DB Session（由呼叫端注入）。
        reporter: 進度回報（pipeline-operations-center §3A.4）。``None``
            時走 NoopProgressReporter。
        classifier: 分類判定（測試注入用）；``None`` 時從 DB 載入。

    Returns:
        ClassifySummary 統計摘要。
    """
    if reporter is None:
        reporter = NoopProgressReporter()

    if classifier is None:
        classifier = await Classifier.load(session)

    transactions = await fetch_unclassified_transactions(session)
    await reporter.stage_started("classify", total=len(transactions))
    if not transactions:
        logger.info("沒有未分類的交易，跳過分類")
        return ClassifySummary(classified_count=0, skipped_count=0, total_count=0)

    counts: Counter[DecisionSource] = Counter()
    processed = 0

    # Accumulate {category: [transactions]} so writes collapse into one UPDATE
    # per distinct category instead of one per row.
    pending_updates: defaultdict[str, list[Transaction]] = defaultdict(list)

    for txn in transactions:
        try:
            decision = await classifier.decide(txn)
            counts[decision.source] += 1
            if decision.category is not None:
                pending_updates[decision.category].append(txn)
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

    manual_override_count = counts[DecisionSource.MANUAL_OVERRIDE]
    user_rule_hits = counts[DecisionSource.USER_RULE]
    engine_hits = counts[DecisionSource.KEYWORD]
    unclassified = counts[DecisionSource.DEFAULT]
    # 與既有契約相容：classified_count 含所有寫入 category 的 row（即使是
    # DEFAULT_CATEGORY 也算，與 manual_override 的 skip 區分）
    classified_count = user_rule_hits + engine_hits + unclassified
    logger.info(
        "classify done: manual=%d user=%d keyword=%d unclassified=%d total=%d",
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


async def run_reclassify_job(
    session: AsyncSession, *, classifier: Classifier | None = None
) -> ClassifySummary:
    """對所有交易重新取得分類判定，只寫入消費類別有變動者。

    分類判定（:class:`ccas.classifier.Classifier`）以最新規則逐筆重算；
    手動分類覆寫的交易一律跳過，保留使用者編輯結果
    （§15.1：「手動改 category → 重跑 pipeline 5 次 → category 不變」）。

    Args:
        session: 非同步 DB Session（由呼叫端注入）。
        classifier: 分類判定（測試注入用）；``None`` 時從 DB 載入。

    Returns:
        ClassifySummary 統計摘要；``skipped_count`` / ``manual_override_count``
        會包含被 manual_override 跳過的交易數。
    """
    if classifier is None:
        classifier = await Classifier.load(session)

    transactions = await fetch_all_transactions(session)
    if not transactions:
        logger.info("沒有任何交易，跳過重跑分類")
        return ClassifySummary(classified_count=0, skipped_count=0, total_count=0)

    classified_count = 0
    unchanged_count = 0
    manual_override_count = 0
    # Accumulate {category: [transactions]} so writes collapse into one UPDATE
    # per distinct category instead of one per row.
    pending_updates: defaultdict[str, list[Transaction]] = defaultdict(list)
    for txn in transactions:
        decision = await classifier.decide(txn)
        if decision.category is None:
            manual_override_count += 1
        elif txn.category == decision.category:
            unchanged_count += 1
        else:
            pending_updates[decision.category].append(txn)
            classified_count += 1
    skipped_count = manual_override_count + unchanged_count

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
