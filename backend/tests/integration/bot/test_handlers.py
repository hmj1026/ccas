"""Bot handler 的整合測試。

使用 in-memory SQLite 測試 /paid 狀態更新與查詢指令。
"""

from datetime import date, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.bot import queries
from ccas.bot.formatting import format_status
from ccas.storage.models import BankConfig, Bill, Transaction
from tests.integration.conftest import make_ctbc_bank_config


async def _seed_bank_configs(session: AsyncSession) -> None:
    """建立測試用銀行設定。"""
    session.add_all(
        [
            make_ctbc_bank_config(),
            BankConfig(
                bank_code="CATHAY",
                bank_name="國泰世華",
                gmail_filter="from:cathay",
            ),
        ]
    )
    await session.flush()


async def _seed_bills(session: AsyncSession) -> tuple[Bill, Bill]:
    """建立測試帳單：一筆未繳、一筆已繳。"""
    bill_unpaid = Bill(
        bank_code="CTBC",
        billing_month="2026-03",
        total_amount=5000,
        due_date=date(2026, 4, 15),
        is_paid=False,
    )
    bill_paid = Bill(
        bank_code="CATHAY",
        billing_month="2026-03",
        total_amount=8000,
        due_date=date(2026, 4, 10),
        is_paid=True,
    )
    session.add_all([bill_unpaid, bill_paid])
    await session.flush()
    return bill_unpaid, bill_paid


@pytest.mark.asyncio
class TestPaidHandler:
    """測試 /paid 的帳單狀態更新。"""

    async def test_mark_bill_as_paid(self, db_session: AsyncSession):
        await _seed_bank_configs(db_session)
        bill_unpaid, _ = await _seed_bills(db_session)

        bill = await queries.fetch_bill_by_id(db_session, bill_unpaid.id)
        assert bill is not None
        assert bill.is_paid is False

        bill.is_paid = True
        await db_session.commit()

        refreshed = await queries.fetch_bill_by_id(db_session, bill_unpaid.id)
        assert refreshed is not None
        assert refreshed.is_paid is True

    async def test_idempotent_paid(self, db_session: AsyncSession):
        await _seed_bank_configs(db_session)
        _, bill_paid = await _seed_bills(db_session)

        bill = await queries.fetch_bill_by_id(db_session, bill_paid.id)
        assert bill is not None
        assert bill.is_paid is True

        # Second mark should not error
        bill.is_paid = True
        await db_session.commit()

        refreshed = await queries.fetch_bill_by_id(db_session, bill_paid.id)
        assert refreshed is not None
        assert refreshed.is_paid is True

    async def test_bill_not_found(self, db_session: AsyncSession):
        bill = await queries.fetch_bill_by_id(db_session, 99999)
        assert bill is None


@pytest.mark.asyncio
class TestQueryHandlers:
    """測試查詢指令的資料存取層。"""

    async def test_fetch_bills_by_month_all(self, db_session: AsyncSession):
        await _seed_bank_configs(db_session)
        await _seed_bills(db_session)
        bills = await queries.fetch_bills_by_month(db_session, "2026-03")
        assert len(bills) == 2

    async def test_fetch_bills_by_month_unpaid(self, db_session: AsyncSession):
        await _seed_bank_configs(db_session)
        await _seed_bills(db_session)
        bills = await queries.fetch_bills_by_month(
            db_session, "2026-03", paid_filter="unpaid"
        )
        assert len(bills) == 1
        assert bills[0].is_paid is False

    async def test_fetch_bills_by_month_paid(self, db_session: AsyncSession):
        await _seed_bank_configs(db_session)
        await _seed_bills(db_session)
        bills = await queries.fetch_bills_by_month(
            db_session, "2026-03", paid_filter="paid"
        )
        assert len(bills) == 1
        assert bills[0].is_paid is True

    async def test_fetch_upcoming_bills(self, db_session: AsyncSession):
        today = date.today()
        bill = Bill(
            bank_code="CTBC",
            billing_month="2026-03",
            total_amount=5000,
            due_date=today + timedelta(days=3),
            is_paid=False,
        )
        db_session.add(bill)
        await db_session.flush()

        result = await queries.fetch_upcoming_bills(db_session, today=today, days=7)
        assert len(result) == 1
        assert result[0].id == bill.id

    async def test_fetch_upcoming_excludes_paid(self, db_session: AsyncSession):
        today = date.today()
        bill = Bill(
            bank_code="CTBC",
            billing_month="2026-03",
            total_amount=5000,
            due_date=today + timedelta(days=3),
            is_paid=True,
        )
        db_session.add(bill)
        await db_session.flush()

        result = await queries.fetch_upcoming_bills(db_session, today=today, days=7)
        assert len(result) == 0

    async def test_fetch_bank_names(self, db_session: AsyncSession):
        await _seed_bank_configs(db_session)
        names = await queries.fetch_bank_names(db_session)
        assert names == {"CTBC": "中國信託", "CATHAY": "國泰世華"}

    async def test_fetch_category_summary(self, db_session: AsyncSession):
        bill = Bill(
            bank_code="CTBC",
            billing_month="2026-03",
            total_amount=5000,
            due_date=date(2026, 4, 15),
        )
        db_session.add(bill)
        await db_session.flush()

        db_session.add_all(
            [
                Transaction(
                    bill_id=bill.id,
                    trans_date=date(2026, 3, 1),
                    merchant="星巴克",
                    amount=300,
                    category="餐飲",
                ),
                Transaction(
                    bill_id=bill.id,
                    trans_date=date(2026, 3, 2),
                    merchant="台灣大車隊",
                    amount=200,
                    category="交通",
                ),
            ]
        )
        await db_session.flush()

        rows = await queries.fetch_category_summary(db_session, "2026-03")
        assert len(rows) == 2
        # Ordered by amount desc
        assert rows[0][0] == "餐飲"
        assert rows[0][1] == 300
        assert rows[1][0] == "交通"
        assert rows[1][1] == 200

    async def test_multi_bank_status_grouping(self, db_session: AsyncSession):
        await _seed_bank_configs(db_session)
        await _seed_bills(db_session)

        bills = await queries.fetch_bills_by_month(db_session, "2026-03")
        bank_names = await queries.fetch_bank_names(db_session)
        text = format_status(bills, bank_names)

        assert "中國信託" in text
        assert "國泰世華" in text
