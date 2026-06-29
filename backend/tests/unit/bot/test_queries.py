"""ccas.bot.queries 的單元測試。

以 in-memory SQLite async engine + 真實 ORM model 執行查詢，
確保各查詢 helper 的 SQL 實際被執行（filter / order / group / coalesce）。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import date, timedelta

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ccas.bot.queries import (
    fetch_bank_names,
    fetch_bill_by_id,
    fetch_bills_by_month,
    fetch_category_summary,
    fetch_upcoming_bills,
)
from ccas.constants import DEFAULT_CATEGORY
from ccas.storage.models import BankConfig, Base, Bill, Transaction


@pytest.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


async def _add_bill(
    session: AsyncSession,
    *,
    bank_code: str,
    billing_month: str,
    due_date: date,
    is_paid: bool = False,
    total_amount: int = 1000,
) -> Bill:
    bill = Bill(
        bank_code=bank_code,
        billing_month=billing_month,
        total_amount=total_amount,
        due_date=due_date,
        is_paid=is_paid,
    )
    session.add(bill)
    await session.flush()
    return bill


async def _add_transaction(
    session: AsyncSession,
    *,
    bill_id: int,
    amount: int,
    category: str | None,
    merchant: str = "M",
) -> None:
    session.add(
        Transaction(
            bill_id=bill_id,
            trans_date=date.today(),
            merchant=merchant,
            amount=amount,
            currency="TWD",
            category=category,
        )
    )


class TestFetchBillsByMonth:
    async def test_returns_all_bills_for_month_ordered_by_bank_code(
        self, session: AsyncSession
    ) -> None:
        await _add_bill(
            session, bank_code="ESUN", billing_month="2026-06", due_date=date.today()
        )
        await _add_bill(
            session, bank_code="CTBC", billing_month="2026-06", due_date=date.today()
        )
        await _add_bill(
            session, bank_code="CTBC", billing_month="2026-05", due_date=date.today()
        )
        await session.commit()

        bills = await fetch_bills_by_month(session, "2026-06")

        assert [b.bank_code for b in bills] == ["CTBC", "ESUN"]

    async def test_eager_loads_transactions(self, session: AsyncSession) -> None:
        bill = await _add_bill(
            session, bank_code="CTBC", billing_month="2026-06", due_date=date.today()
        )
        await _add_transaction(session, bill_id=bill.id, amount=500, category="餐飲")
        await session.commit()
        session.expunge_all()

        bills = await fetch_bills_by_month(session, "2026-06")

        # selectinload 已預載，存取 .transactions 不會觸發 lazy IO error
        assert len(bills) == 1
        assert len(bills[0].transactions) == 1

    async def test_unpaid_filter_excludes_paid(self, session: AsyncSession) -> None:
        await _add_bill(
            session,
            bank_code="CTBC",
            billing_month="2026-06",
            due_date=date.today(),
            is_paid=True,
        )
        await _add_bill(
            session,
            bank_code="ESUN",
            billing_month="2026-06",
            due_date=date.today(),
            is_paid=False,
        )
        await session.commit()

        bills = await fetch_bills_by_month(session, "2026-06", paid_filter="unpaid")

        assert [b.bank_code for b in bills] == ["ESUN"]

    async def test_paid_filter_excludes_unpaid(self, session: AsyncSession) -> None:
        await _add_bill(
            session,
            bank_code="CTBC",
            billing_month="2026-06",
            due_date=date.today(),
            is_paid=True,
        )
        await _add_bill(
            session,
            bank_code="ESUN",
            billing_month="2026-06",
            due_date=date.today(),
            is_paid=False,
        )
        await session.commit()

        bills = await fetch_bills_by_month(session, "2026-06", paid_filter="paid")

        assert [b.bank_code for b in bills] == ["CTBC"]

    async def test_empty_month_returns_empty(self, session: AsyncSession) -> None:
        assert await fetch_bills_by_month(session, "2099-01") == []


class TestFetchUpcomingBills:
    async def test_defaults_today_to_date_today(self, session: AsyncSession) -> None:
        # due 在預設 7 天窗內，today=None 應自動採用 date.today()
        await _add_bill(
            session,
            bank_code="CTBC",
            billing_month="2026-06",
            due_date=date.today() + timedelta(days=3),
        )
        await session.commit()

        bills = await fetch_upcoming_bills(session)

        assert len(bills) == 1

    async def test_includes_only_unpaid_within_window(
        self, session: AsyncSession
    ) -> None:
        base = date(2026, 6, 1)
        # 窗內未繳 → 納入
        await _add_bill(
            session,
            bank_code="CTBC",
            billing_month="2026-06",
            due_date=base + timedelta(days=2),
        )
        # 窗內但已繳 → 排除
        await _add_bill(
            session,
            bank_code="ESUN",
            billing_month="2026-06",
            due_date=base + timedelta(days=2),
            is_paid=True,
        )
        # 過期（早於 today）→ 排除
        await _add_bill(
            session,
            bank_code="FUBON",
            billing_month="2026-05",
            due_date=base - timedelta(days=1),
        )
        # 超出窗（晚於 today+days）→ 排除
        await _add_bill(
            session,
            bank_code="TAISHIN",
            billing_month="2026-07",
            due_date=base + timedelta(days=30),
        )
        await session.commit()

        bills = await fetch_upcoming_bills(session, today=base, days=7)

        assert [b.bank_code for b in bills] == ["CTBC"]

    async def test_ordered_by_due_date_then_bank_code(
        self, session: AsyncSession
    ) -> None:
        base = date(2026, 6, 1)
        await _add_bill(
            session,
            bank_code="ESUN",
            billing_month="2026-06",
            due_date=base + timedelta(days=5),
        )
        await _add_bill(
            session,
            bank_code="ZBANK",
            billing_month="2026-06",
            due_date=base + timedelta(days=1),
        )
        await _add_bill(
            session,
            bank_code="ABANK",
            billing_month="2026-06",
            due_date=base + timedelta(days=1),
        )
        await session.commit()

        bills = await fetch_upcoming_bills(session, today=base, days=7)

        # due_date 先 (day+1 兩筆 → ABANK, ZBANK)，再 day+5 (ESUN)
        assert [b.bank_code for b in bills] == ["ABANK", "ZBANK", "ESUN"]

    async def test_boundary_dates_inclusive(self, session: AsyncSession) -> None:
        base = date(2026, 6, 1)
        # due == today（下界）
        await _add_bill(
            session, bank_code="CTBC", billing_month="2026-06", due_date=base
        )
        # due == today+days（上界）
        await _add_bill(
            session,
            bank_code="ESUN",
            billing_month="2026-06",
            due_date=base + timedelta(days=7),
        )
        await session.commit()

        bills = await fetch_upcoming_bills(session, today=base, days=7)

        assert {b.bank_code for b in bills} == {"CTBC", "ESUN"}


class TestFetchBillById:
    async def test_returns_bill_when_found(self, session: AsyncSession) -> None:
        bill = await _add_bill(
            session, bank_code="CTBC", billing_month="2026-06", due_date=date.today()
        )
        await session.commit()

        found = await fetch_bill_by_id(session, bill.id)

        assert found is not None
        assert found.id == bill.id
        assert found.bank_code == "CTBC"

    async def test_returns_none_when_missing(self, session: AsyncSession) -> None:
        assert await fetch_bill_by_id(session, 999999) is None


class TestFetchCategorySummary:
    async def test_groups_and_sums_descending(self, session: AsyncSession) -> None:
        bill = await _add_bill(
            session, bank_code="CTBC", billing_month="2026-06", due_date=date.today()
        )
        await _add_transaction(session, bill_id=bill.id, amount=3000, category="餐飲")
        await _add_transaction(session, bill_id=bill.id, amount=1000, category="餐飲")
        await _add_transaction(session, bill_id=bill.id, amount=5000, category="交通")
        await session.commit()

        summary = await fetch_category_summary(session, "2026-06")

        # 交通 5000 > 餐飲 4000，依金額降冪
        assert summary == [("交通", 5000), ("餐飲", 4000)]

    async def test_null_category_uses_default(self, session: AsyncSession) -> None:
        bill = await _add_bill(
            session, bank_code="CTBC", billing_month="2026-06", due_date=date.today()
        )
        await _add_transaction(session, bill_id=bill.id, amount=800, category=None)
        await session.commit()

        summary = await fetch_category_summary(session, "2026-06")

        assert summary == [(DEFAULT_CATEGORY, 800)]

    async def test_excludes_other_months(self, session: AsyncSession) -> None:
        bill_jun = await _add_bill(
            session, bank_code="CTBC", billing_month="2026-06", due_date=date.today()
        )
        bill_may = await _add_bill(
            session, bank_code="CTBC", billing_month="2026-05", due_date=date.today()
        )
        await _add_transaction(
            session, bill_id=bill_jun.id, amount=200, category="餐飲"
        )
        await _add_transaction(
            session, bill_id=bill_may.id, amount=999, category="餐飲"
        )
        await session.commit()

        summary = await fetch_category_summary(session, "2026-06")

        assert summary == [("餐飲", 200)]

    async def test_empty_month_returns_empty(self, session: AsyncSession) -> None:
        assert await fetch_category_summary(session, "2099-01") == []


class TestFetchBankNames:
    async def test_returns_code_to_name_mapping(self, session: AsyncSession) -> None:
        session.add(
            BankConfig(bank_code="CTBC", bank_name="中國信託", gmail_filter="from:ctbc")
        )
        session.add(
            BankConfig(bank_code="ESUN", bank_name="玉山銀行", gmail_filter="from:esun")
        )
        await session.commit()

        assert await fetch_bank_names(session) == {
            "CTBC": "中國信託",
            "ESUN": "玉山銀行",
        }

    async def test_empty_returns_empty_dict(self, session: AsyncSession) -> None:
        assert await fetch_bank_names(session) == {}
