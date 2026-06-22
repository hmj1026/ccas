"""classifier job 的整合測試。

使用 in-memory SQLite 測試完整的分類與重跑分類流程。
"""

from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.classifier.job import run_classify_job, run_reclassify_job
from ccas.classifier.rules import load_rules
from ccas.storage.models import Bill, Category, Transaction


async def _seed_categories(session: AsyncSession) -> None:
    """建立測試用分類規則。"""
    session.add_all(
        [
            Category(keyword="星巴克", category="餐飲"),
            Category(keyword="台灣大哥大", category="通訊"),
            Category(keyword="台灣", category="其他"),
            Category(keyword="AMAZON", category="購物"),
        ]
    )
    await session.flush()


async def _seed_bill_with_transactions(
    session: AsyncSession,
    merchants: list[str],
) -> Bill:
    """建立一筆帳單與多筆交易，category 皆為 NULL。"""
    bill = Bill(
        bank_code="CTBC",
        billing_month="2026-03",
        total_amount=5000,
        due_date=date(2026, 4, 15),
    )
    session.add(bill)
    await session.flush()

    for merchant in merchants:
        txn = Transaction(
            bill_id=bill.id,
            trans_date=date(2026, 3, 1),
            merchant=merchant,
            amount=100,
        )
        session.add(txn)
    await session.flush()
    return bill


class TestLoadRulesIntegration:
    @pytest.mark.asyncio
    async def test_load_from_empty_table(self, db_session: AsyncSession) -> None:
        rule_set = await load_rules(db_session)
        assert rule_set.count == 0

    @pytest.mark.asyncio
    async def test_load_all_rules(self, db_session: AsyncSession) -> None:
        await _seed_categories(db_session)
        rule_set = await load_rules(db_session)
        assert rule_set.count == 4

    @pytest.mark.asyncio
    async def test_reload_reflects_changes(self, db_session: AsyncSession) -> None:
        """規則重載後反映資料表變更。"""
        await _seed_categories(db_session)
        old_rules = await load_rules(db_session)
        assert old_rules.count == 4

        # 新增一筆規則
        db_session.add(Category(keyword="全聯", category="超市"))
        await db_session.flush()

        new_rules = await load_rules(db_session)
        assert new_rules.count == 5
        # 舊 snapshot 不受影響
        assert old_rules.count == 4


class TestRunClassifyJob:
    @pytest.mark.asyncio
    async def test_classify_new_transactions(self, db_session: AsyncSession) -> None:
        await _seed_categories(db_session)
        await _seed_bill_with_transactions(
            db_session,
            ["星巴克咖啡 信義店", "台灣大哥大月租費", "未知商家"],
        )

        summary = await run_classify_job(db_session)

        assert summary.classified_count == 3
        assert summary.total_count == 3

        # 驗證分類結果
        result = await db_session.execute(select(Transaction).order_by(Transaction.id))
        txns = result.scalars().all()
        assert txns[0].category == "餐飲"
        assert txns[1].category == "通訊"  # 最長關鍵字 "台灣大哥大" > "台灣"
        assert txns[2].category == "未分類"

    @pytest.mark.asyncio
    async def test_skip_already_classified(self, db_session: AsyncSession) -> None:
        """已有分類的交易不會被 run_classify_job 處理。"""
        await _seed_categories(db_session)
        await _seed_bill_with_transactions(db_session, ["星巴克"])

        # 手動設定分類
        result = await db_session.execute(select(Transaction))
        txn = result.scalar_one()
        txn.category = "手動分類"
        await db_session.flush()

        summary = await run_classify_job(db_session)
        assert summary.total_count == 0  # 沒有未分類交易

        # 確認原始分類未被改寫
        await db_session.refresh(txn)
        assert txn.category == "手動分類"

    @pytest.mark.asyncio
    async def test_no_transactions(self, db_session: AsyncSession) -> None:
        summary = await run_classify_job(db_session)
        assert summary.classified_count == 0
        assert summary.total_count == 0

    @pytest.mark.asyncio
    async def test_case_insensitive(self, db_session: AsyncSession) -> None:
        await _seed_categories(db_session)
        await _seed_bill_with_transactions(db_session, ["amazon prime 月費"])

        await run_classify_job(db_session)

        result = await db_session.execute(select(Transaction))
        txn = result.scalar_one()
        assert txn.category == "購物"


class TestRunReclassifyJob:
    @pytest.mark.asyncio
    async def test_reclassify_updates_category(self, db_session: AsyncSession) -> None:
        """重跑分類會以最新規則更新所有交易。"""
        await _seed_categories(db_session)
        await _seed_bill_with_transactions(db_session, ["星巴克咖啡"])

        # 先分類
        await run_classify_job(db_session)
        result = await db_session.execute(select(Transaction))
        txn = result.scalar_one()
        assert txn.category == "餐飲"

        # 修改規則：星巴克 → 飲料
        cat_result = await db_session.execute(
            select(Category).where(Category.keyword == "星巴克")
        )
        cat = cat_result.scalar_one()
        cat.category = "飲料"
        await db_session.flush()

        # 重跑分類
        summary = await run_reclassify_job(db_session)
        assert summary.classified_count == 1  # 1 筆更新

        await db_session.refresh(txn)
        assert txn.category == "飲料"

    @pytest.mark.asyncio
    async def test_reclassify_preserves_original_fields(
        self, db_session: AsyncSession
    ) -> None:
        """重跑分類只改 category，不改寫原始欄位。"""
        await _seed_categories(db_session)
        await _seed_bill_with_transactions(db_session, ["星巴克咖啡"])

        result = await db_session.execute(select(Transaction))
        txn = result.scalar_one()
        original_merchant = txn.merchant
        original_amount = txn.amount
        original_trans_date = txn.trans_date

        await run_reclassify_job(db_session)

        await db_session.refresh(txn)
        assert txn.merchant == original_merchant
        assert txn.amount == original_amount
        assert txn.trans_date == original_trans_date

    @pytest.mark.asyncio
    async def test_reclassify_skips_unchanged(self, db_session: AsyncSession) -> None:
        """分類結果不變時不做更新。"""
        await _seed_categories(db_session)
        await _seed_bill_with_transactions(db_session, ["星巴克咖啡"])

        await run_classify_job(db_session)
        summary = await run_reclassify_job(db_session)

        # 分類沒變，應該全部 skipped
        assert summary.skipped_count == 1
        assert summary.classified_count == 0

    @pytest.mark.asyncio
    async def test_no_transactions(self, db_session: AsyncSession) -> None:
        summary = await run_reclassify_job(db_session)
        assert summary.classified_count == 0
        assert summary.total_count == 0


class TestClassifyProgressReporterGuard:
    """progress reporter 失敗不得中止 classify 批次（與其他四階段一致）。"""

    @pytest.mark.asyncio
    async def test_reporter_failure_does_not_abort_batch(
        self, db_session: AsyncSession
    ) -> None:
        await _seed_categories(db_session)
        await _seed_bill_with_transactions(
            db_session, ["星巴克", "台灣大哥大", "AMAZON"]
        )
        await db_session.commit()

        class _BoomReporter:
            """每次 stage_item_done 都拋例外，模擬 SQLite busy 等暫時故障。"""

            async def stage_started(self, stage: str, total: int) -> None: ...

            async def stage_item_done(self, stage: str, processed: int) -> None:
                raise RuntimeError("progress reporter 暫時故障")

            async def stage_finished(
                self, stage, ok, fail, elapsed_ms, **kw
            ) -> None: ...

        await run_classify_job(db_session, reporter=_BoomReporter())

        # reporter 持續失敗，但所有交易仍應被分類並 commit（progress 純 UI）。
        txns = (await db_session.execute(select(Transaction))).scalars().all()
        assert len(txns) == 3
        assert all(t.category is not None for t in txns)
