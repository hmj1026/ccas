"""classifier job 批次 category 更新的單元測試。

驗證 run_classify_job / run_reclassify_job 將逐筆 UPDATE 聚合為
「每個 distinct category 一條 UPDATE」（K 條而非 N 條），
且 run_reclassify_job 保留 ``txn.category == new_category`` 的跳過邏輯。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

from ccas.classifier.job import (
    _flush_category_updates,
    run_classify_job,
    run_reclassify_job,
)
from ccas.classifier.user_rules import UserRuleMatcher
from ccas.storage.models import Transaction

_EMPTY_MATCHER = UserRuleMatcher([])


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


async def test_classify_batches_rows_into_one_update_per_category() -> None:
    """4 rows / 2 categories → 2 UPDATEs; summary counts unchanged."""
    session = AsyncMock()

    txns = [
        _txn(1, "星巴克"),
        _txn(2, "路易莎"),
        _txn(3, "台灣大哥大"),
        _txn(4, "中華電信"),
    ]
    categories = {
        "星巴克": "餐飲",
        "路易莎": "餐飲",
        "台灣大哥大": "通訊",
        "中華電信": "通訊",
    }

    with (
        patch(
            "ccas.classifier.job.UserRuleMatcher.load",
            new=AsyncMock(return_value=_EMPTY_MATCHER),
        ),
        patch("ccas.classifier.job.load_rules", new=AsyncMock(return_value={})),
        patch(
            "ccas.classifier.job.fetch_unclassified_transactions",
            new=AsyncMock(return_value=txns),
        ),
        patch(
            "ccas.classifier.job.classify",
            new=lambda merchant, _rules: categories[merchant],
        ),
    ):
        summary = await run_classify_job(session)

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
        # Unchanged: classify yields the current category → skip.
        _txn(1, "星巴克", category="餐飲"),
        # Changed: 餐飲 → 通訊.
        _txn(2, "台灣大哥大", category="餐飲"),
        # Manual override: always skipped.
        _txn(3, "路易莎", category="自訂", manual_override=True),
    ]
    categories = {"星巴克": "餐飲", "台灣大哥大": "通訊"}

    def fake_classify(merchant: str, _rules: Any) -> str:
        return categories[merchant]

    with (
        patch(
            "ccas.classifier.job.UserRuleMatcher.load",
            new=AsyncMock(return_value=_EMPTY_MATCHER),
        ),
        patch("ccas.classifier.job.load_rules", new=AsyncMock(return_value={})),
        patch(
            "ccas.classifier.job.fetch_all_transactions",
            new=AsyncMock(return_value=txns),
        ),
        patch("ccas.classifier.job.classify", new=fake_classify),
    ):
        summary = await run_reclassify_job(session)

    assert session.execute.await_count == 1
    assert _executed_updates(session) == {"通訊": [2]}
    assert [t.category for t in txns] == ["餐飲", "通訊", "自訂"]
    assert summary.classified_count == 1
    assert summary.skipped_count == 2
    assert summary.manual_override_count == 1
    session.commit.assert_awaited_once()
