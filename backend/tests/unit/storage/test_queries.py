"""ccas.storage.queries.fetch_bank_names 的單元測試。

cache 已移除（P3：跨 process 各持陳舊副本，Setup UI 改名最久 5 分鐘才生效），
``fetch_bank_names`` 每次都重新查詢；測試聚焦於 fresh-read 語意。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import date

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ccas.storage.models import (
    BankConfig,
    Base,
    Bill,
    Budget,
    BudgetScope,
    Transaction,
)
from ccas.storage.queries import aggregate_current_periods, fetch_bank_names
from ccas.tools.bank_configs import BankConfigSpec, sync_bank_configs


@pytest.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


async def _seed_bank(session: AsyncSession, code: str, name: str) -> None:
    session.add(BankConfig(bank_code=code, bank_name=name, gmail_filter=f"from:{code}"))
    await session.commit()


class TestFetchBankNames:
    async def test_returns_bank_code_to_name_mapping(
        self, session: AsyncSession
    ) -> None:
        await _seed_bank(session, "CTBC", "中國信託")
        assert await fetch_bank_names(session) == {"CTBC": "中國信託"}

    async def test_reflects_new_rows_immediately(self, session: AsyncSession) -> None:
        await _seed_bank(session, "CTBC", "中國信託")
        assert await fetch_bank_names(session) == {"CTBC": "中國信託"}

        # 無快取：新增的 bank 立刻可見，不需等待 TTL 或手動 invalidate。
        await _seed_bank(session, "ESUN", "玉山銀行")
        assert await fetch_bank_names(session) == {
            "CTBC": "中國信託",
            "ESUN": "玉山銀行",
        }

    async def test_returned_dict_is_independent(self, session: AsyncSession) -> None:
        await _seed_bank(session, "CTBC", "中國信託")
        first = await fetch_bank_names(session)
        first["HACK"] = "mutated"

        assert await fetch_bank_names(session) == {"CTBC": "中國信託"}


async def _seed_period_spend(session: AsyncSession, period: str) -> None:
    """CTBC bill in ``period`` with 餐飲 3000 + 交通 5000（總額 8000）。"""
    session.add(
        BankConfig(bank_code="CTBC", bank_name="中國信託", gmail_filter="from:ctbc")
    )
    bill = Bill(
        bank_code="CTBC",
        billing_month=period,
        total_amount=8000,
        due_date=date.today(),
        is_paid=False,
    )
    session.add(bill)
    await session.flush()
    for amount, category in [(3000, "餐飲"), (5000, "交通")]:
        session.add(
            Transaction(
                bill_id=bill.id,
                trans_date=date.today(),
                merchant=f"M-{amount}",
                amount=amount,
                currency="TWD",
                category=category,
            )
        )
    await session.commit()


def _budget(scope: BudgetScope, ref: str | None) -> Budget:
    return Budget(
        scope=scope,
        scope_ref=ref,
        amount_ntd=10000,
        alert_threshold_percent=80,
        enabled=True,
    )


class TestAggregateCurrentPeriods:
    """R-budget-N+1：批次聚合各 scope 當月累計，查詢數恆為 O(1)。"""

    async def test_empty_budgets_returns_empty(self, session: AsyncSession) -> None:
        assert await aggregate_current_periods(session, [], "2026-06") == {}

    async def test_maps_each_scope_correctly(self, session: AsyncSession) -> None:
        period = "2026-06"
        await _seed_period_spend(session, period)
        budgets = [
            _budget(BudgetScope.MONTHLY_TOTAL, None),
            _budget(BudgetScope.MONTHLY_CATEGORY, "餐飲"),
            _budget(BudgetScope.MONTHLY_BANK, "CTBC"),
            _budget(BudgetScope.MONTHLY_CATEGORY, "不存在的類別"),
        ]
        session.add_all(budgets)
        await session.commit()

        result = await aggregate_current_periods(session, budgets, period)
        assert result[budgets[0].id] == 8000  # monthly_total
        assert result[budgets[1].id] == 3000  # 餐飲
        assert result[budgets[2].id] == 8000  # CTBC bank
        assert result[budgets[3].id] == 0  # scope_ref 不匹配 → 0

    async def test_query_count_bounded_regardless_of_budget_count(
        self, session: AsyncSession
    ) -> None:
        period = "2026-06"
        await _seed_period_spend(session, period)
        budgets = (
            [_budget(BudgetScope.MONTHLY_TOTAL, None) for _ in range(20)]
            + [_budget(BudgetScope.MONTHLY_CATEGORY, "餐飲") for _ in range(20)]
            + [_budget(BudgetScope.MONTHLY_BANK, "CTBC") for _ in range(20)]
        )
        session.add_all(budgets)
        await session.commit()

        selects = 0

        def _count(conn, cursor, statement, params, context, executemany):  # noqa: ANN001,ANN202
            nonlocal selects
            if statement.lstrip().upper().startswith("SELECT"):
                selects += 1

        engine = session.bind
        assert engine is not None
        event.listen(engine.sync_engine, "after_cursor_execute", _count)
        try:
            result = await aggregate_current_periods(session, budgets, period)
        finally:
            event.remove(engine.sync_engine, "after_cursor_execute", _count)

        # 三種 scope 恰各一次 grouped query（共 3 次）；不隨 60 筆 budget 增長。
        # 用 ==（非 <=）才能讓退化回 N+1 的回歸在小資料集上也被攔下。
        assert selects == 3
        assert result[budgets[0].id] == 8000


class TestSyncBankConfigsVisibility:
    async def test_apply_sync_is_visible_immediately(
        self, session: AsyncSession
    ) -> None:
        await _seed_bank(session, "CTBC", "中國信託")
        await fetch_bank_names(session)

        specs = [
            BankConfigSpec(
                bank_code="ESUN",
                bank_name="玉山銀行",
                gmail_filter="from:esun",
            )
        ]
        await sync_bank_configs(session, specs, apply_changes=True)

        assert await fetch_bank_names(session) == {
            "CTBC": "中國信託",
            "ESUN": "玉山銀行",
        }
