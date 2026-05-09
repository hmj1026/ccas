"""run_classify_job 優先序整合測試（bills-management-and-insights §2.5）。

驗證 4 條路徑：
(a) ``manual_category_override=True`` 時 skip 全部規則
(b) user rules 命中（即使 keyword engine 也能匹配）
(c) user rules 不命中 fallback 到 keyword engine
(d) 兩者皆不命中走 ``DEFAULT_CATEGORY``
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.classifier.engine import DEFAULT_CATEGORY
from ccas.classifier.job import run_classify_job
from ccas.storage.models import (
    Bill,
    Category,
    PatternType,
    Transaction,
    UserClassificationRule,
)


async def _seed_bill(session: AsyncSession) -> Bill:
    bill = Bill(
        bank_code="CTBC",
        billing_month="2026-04",
        total_amount=1000,
        due_date=date(2026, 5, 15),
    )
    session.add(bill)
    await session.flush()
    return bill


class TestClassifyPriority:
    async def test_manual_override_skips_all_rules(
        self, db_session: AsyncSession
    ) -> None:
        """(a) manual_category_override=True 即使 user_rules / engine 命中也不改。"""
        food = Category(keyword="星巴克", category="餐飲")
        db_session.add(food)
        await db_session.flush()

        bill = await _seed_bill(db_session)
        manual_txn = Transaction(
            bill_id=bill.id,
            trans_date=date(2026, 4, 1),
            merchant="星巴克咖啡",
            amount=150,
            category="使用者自訂",
            manual_category_override=True,
        )
        db_session.add(manual_txn)
        await db_session.flush()

        # 為了讓 fetch_unclassified_transactions 看得到 row，category 必須 NULL；
        # 建立另一筆 manual_override=True 但 category 未填的 row 驗證 skip 行為。
        manual_unclassified = Transaction(
            bill_id=bill.id,
            trans_date=date(2026, 4, 2),
            merchant="星巴克咖啡",
            amount=200,
            category=None,
            manual_category_override=True,
        )
        db_session.add(manual_unclassified)
        await db_session.flush()

        summary = await run_classify_job(db_session)

        assert summary.manual_override_count == 1
        assert summary.user_rule_hits == 0
        assert summary.engine_hits == 0

        await db_session.refresh(manual_unclassified)
        # manual_override skip → category 不被覆寫
        assert manual_unclassified.category is None

    async def test_user_rules_win_over_keyword_engine(
        self, db_session: AsyncSession
    ) -> None:
        """(b) user rule 命中即使 keyword engine 也能匹配。"""
        engine_cat = Category(keyword="星巴克", category="餐飲")
        user_cat = Category(keyword="user-cat-key", category="精品咖啡")
        db_session.add_all([engine_cat, user_cat])
        await db_session.flush()

        db_session.add(
            UserClassificationRule(
                pattern="星巴克",
                pattern_type=PatternType.KEYWORD,
                category_id=user_cat.id,
                priority=10,
                enabled=True,
            )
        )
        await db_session.flush()

        bill = await _seed_bill(db_session)
        txn = Transaction(
            bill_id=bill.id,
            trans_date=date(2026, 4, 1),
            merchant="星巴克信義店",
            amount=150,
        )
        db_session.add(txn)
        await db_session.flush()

        summary = await run_classify_job(db_session)

        assert summary.user_rule_hits == 1
        assert summary.engine_hits == 0
        await db_session.refresh(txn)
        assert txn.category == "精品咖啡"

    async def test_engine_fallback_when_user_rules_miss(
        self, db_session: AsyncSession
    ) -> None:
        """(c) user rules 不命中 → 走 keyword engine。"""
        engine_cat = Category(keyword="加油", category="交通")
        gym_cat = Category(keyword="gym-key", category="健身")
        db_session.add_all([engine_cat, gym_cat])
        await db_session.flush()

        db_session.add(
            UserClassificationRule(
                pattern="World Gym",
                pattern_type=PatternType.KEYWORD,
                category_id=gym_cat.id,
                priority=10,
                enabled=True,
            )
        )
        await db_session.flush()

        bill = await _seed_bill(db_session)
        txn = Transaction(
            bill_id=bill.id,
            trans_date=date(2026, 4, 1),
            merchant="中油加油站",
            amount=500,
        )
        db_session.add(txn)
        await db_session.flush()

        summary = await run_classify_job(db_session)

        assert summary.user_rule_hits == 0
        assert summary.engine_hits == 1
        await db_session.refresh(txn)
        assert txn.category == "交通"

    async def test_default_category_when_all_miss(
        self, db_session: AsyncSession
    ) -> None:
        """(d) 兩者皆不命中 → DEFAULT_CATEGORY。"""
        cat = Category(keyword="加油", category="交通")
        db_session.add(cat)
        await db_session.flush()

        db_session.add(
            UserClassificationRule(
                pattern="UNRELATED",
                pattern_type=PatternType.KEYWORD,
                category_id=cat.id,
                priority=10,
                enabled=True,
            )
        )
        await db_session.flush()

        bill = await _seed_bill(db_session)
        txn = Transaction(
            bill_id=bill.id,
            trans_date=date(2026, 4, 1),
            merchant="某不認識商家",
            amount=300,
        )
        db_session.add(txn)
        await db_session.flush()

        summary = await run_classify_job(db_session)

        assert summary.user_rule_hits == 0
        assert summary.engine_hits == 0
        assert summary.unclassified == 1
        await db_session.refresh(txn)
        assert txn.category == DEFAULT_CATEGORY

    async def test_summary_breakdown_with_mixed_rows(
        self, db_session: AsyncSession
    ) -> None:
        """混合所有路徑：manual / user / engine / unclassified 各一筆。"""
        food = Category(keyword="星巴克", category="餐飲")
        gym = Category(keyword="gym-key", category="健身")
        db_session.add_all([food, gym])
        await db_session.flush()

        db_session.add(
            UserClassificationRule(
                pattern="World Gym",
                pattern_type=PatternType.KEYWORD,
                category_id=gym.id,
                priority=10,
                enabled=True,
            )
        )
        await db_session.flush()

        bill = await _seed_bill(db_session)
        rows = [
            Transaction(
                bill_id=bill.id,
                trans_date=date(2026, 4, 1),
                merchant="未知商家",
                amount=100,
                manual_category_override=True,
            ),
            Transaction(
                bill_id=bill.id,
                trans_date=date(2026, 4, 2),
                merchant="World Gym 三重",
                amount=200,
            ),
            Transaction(
                bill_id=bill.id,
                trans_date=date(2026, 4, 3),
                merchant="星巴克信義",
                amount=150,
            ),
            Transaction(
                bill_id=bill.id,
                trans_date=date(2026, 4, 4),
                merchant="陌生商家",
                amount=80,
            ),
        ]
        for row in rows:
            db_session.add(row)
        await db_session.flush()

        summary = await run_classify_job(db_session)

        assert summary.total_count == 4
        assert summary.manual_override_count == 1
        assert summary.user_rule_hits == 1
        assert summary.engine_hits == 1
        assert summary.unclassified == 1
        # classified_count 兼容契約：含 unclassified
        assert summary.classified_count == 3
        assert summary.skipped_count == 1

        all_txns = (
            (await db_session.execute(select(Transaction).order_by(Transaction.id)))
            .scalars()
            .all()
        )
        assert all_txns[0].category is None  # manual_override skip
        assert all_txns[1].category == "健身"
        assert all_txns[2].category == "餐飲"
        assert all_txns[3].category == DEFAULT_CATEGORY
