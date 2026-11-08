"""classifier job 批次 category 更新的單元測試。

驗證 run_classify_job / run_reclassify_job 將逐筆 UPDATE 聚合為
「每個 distinct category 一條 UPDATE」（K 條而非 N 條），
且 run_reclassify_job 保留 ``txn.category == new_category`` 的跳過邏輯。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from ccas.classifier import Classifier
from ccas.classifier.job import (
    _flush_category_updates,
    run_classify_job,
    run_reclassify_job,
)
from ccas.classifier.rules import ClassificationRule, RuleSet
from ccas.classifier.user_rules import UserRuleMatcher
from ccas.errors import ClassifyError
from ccas.storage.models import Transaction


def _txn(
    txn_id: int,
    merchant: str,
    *,
    category: str | None = None,
    manual_override: bool = False,
) -> Transaction:
    """Build a detached Transaction instance (no DB round-trip needed)."""
    return Transaction(
        id=txn_id,
        merchant=merchant,
        category=category,
        manual_category_override=manual_override,
    )


def _executed_updates(session: AsyncMock) -> dict[str, list[int]]:
    """Extract {category: [txn_ids]} from the UPDATE statements executed."""
    extracted: dict[str, list[int]] = {}
    for call in session.execute.await_args_list:
        params = call.args[0].compile().params
        category = params["category"]
        ids = next(v for k, v in params.items() if isinstance(v, list))
        extracted[category] = list(ids)
    return extracted


async def test_flush_emits_one_update_per_category() -> None:
    session = AsyncMock()
    txn_a = _txn(1, "星巴克")
    txn_b = _txn(2, "台灣大哥大")
    txn_c = _txn(3, "路易莎")

    await _flush_category_updates(
        session,
        {"餐飲": [txn_a, txn_c], "通訊": [txn_b]},
    )

    assert session.execute.await_count == 2
    assert _executed_updates(session) == {"餐飲": [1, 3], "通訊": [2]}
    # Loaded instances are synchronized manually (synchronize_session=False).
    assert txn_a.category == "餐飲"
    assert txn_b.category == "通訊"
    assert txn_c.category == "餐飲"


async def test_flush_with_no_pending_updates_executes_nothing() -> None:
    session = AsyncMock()

    await _flush_category_updates(session, {})

    session.execute.assert_not_awaited()


def _classifier(keyword_categories: dict[str, str]) -> Classifier:
    """In-memory Classifier: no user rules, one keyword rule per merchant."""
    rules = tuple(
        ClassificationRule(rule_id=i, keyword=keyword, category=category)
        for i, (keyword, category) in enumerate(keyword_categories.items(), start=1)
    )
    return Classifier(UserRuleMatcher([]), RuleSet(rules=rules))


async def test_classify_batches_rows_into_one_update_per_category() -> None:
    """4 rows / 2 categories → 2 UPDATEs; summary counts unchanged."""
    session = AsyncMock()

    txns = [
        _txn(1, "星巴克"),
        _txn(2, "路易莎"),
        _txn(3, "台灣大哥大"),
        _txn(4, "中華電信"),
    ]
    classifier = _classifier(
        {"星巴克": "餐飲", "路易莎": "餐飲", "台灣大哥大": "通訊", "中華電信": "通訊"}
    )

    with patch(
        "ccas.classifier.job.fetch_unclassified_transactions",
        new=AsyncMock(return_value=txns),
    ):
        summary = await run_classify_job(session, classifier=classifier)

    assert session.execute.await_count == 2
    assert _executed_updates(session) == {"餐飲": [1, 2], "通訊": [3, 4]}
    # Final per-row categories match the per-row UPDATE behavior.
    assert [t.category for t in txns] == ["餐飲", "餐飲", "通訊", "通訊"]
    assert summary.classified_count == 4
    assert summary.engine_hits == 4
    assert summary.total_count == 4
    session.commit.assert_awaited_once()


async def test_reclassify_batches_and_preserves_skip_logic() -> None:
    """Unchanged category rows are skipped (no UPDATE queued for them)."""
    session = AsyncMock()

    txns = [
        # Unchanged: the decision yields the current category → skip.
        _txn(1, "星巴克", category="餐飲"),
        # Changed: 餐飲 → 通訊.
        _txn(2, "台灣大哥大", category="餐飲"),
        # Manual override: always skipped.
        _txn(3, "路易莎", category="自訂", manual_override=True),
    ]
    classifier = _classifier({"星巴克": "餐飲", "台灣大哥大": "通訊"})

    with patch(
        "ccas.classifier.job.fetch_all_transactions",
        new=AsyncMock(return_value=txns),
    ):
        summary = await run_reclassify_job(session, classifier=classifier)

    assert session.execute.await_count == 1
    assert _executed_updates(session) == {"通訊": [2]}
    assert [t.category for t in txns] == ["餐飲", "通訊", "自訂"]
    assert summary.classified_count == 1
    assert summary.skipped_count == 2
    assert summary.manual_override_count == 1
    session.commit.assert_awaited_once()


async def test_classify_flush_failure_rolls_back_and_raises(caplog) -> None:
    """A commit failure rolls back, logs the affected count, raises ClassifyError."""
    session = AsyncMock()
    session.commit.side_effect = RuntimeError("database is locked")

    txns = [_txn(1, "星巴克"), _txn(2, "路易莎")]
    classifier = _classifier({"星巴克": "餐飲", "路易莎": "餐飲"})
    with (
        patch(
            "ccas.classifier.job.fetch_unclassified_transactions",
            new=AsyncMock(return_value=txns),
        ),
        pytest.raises(ClassifyError),
    ):
        await run_classify_job(session, classifier=classifier)

    session.rollback.assert_awaited_once()
    # affected count (2 pending) appears in the error log
    assert "2 筆" in caplog.text


async def test_reclassify_flush_failure_rolls_back_and_raises(caplog) -> None:
    """reclassify path has the same rollback boundary as classify."""
    session = AsyncMock()
    session.commit.side_effect = RuntimeError("database is locked")

    txns = [_txn(1, "台灣大哥大", category="餐飲")]
    classifier = _classifier({"台灣大哥大": "通訊"})
    with (
        patch(
            "ccas.classifier.job.fetch_all_transactions",
            new=AsyncMock(return_value=txns),
        ),
        pytest.raises(ClassifyError),
    ):
        await run_reclassify_job(session, classifier=classifier)

    session.rollback.assert_awaited_once()
    assert "1 筆" in caplog.text
