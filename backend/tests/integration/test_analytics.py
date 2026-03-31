"""Analytics API 測試。"""

from datetime import date

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.storage.models import BankConfig, Bill, Transaction
from tests.integration.conftest import auth_headers


async def _seed_analytics_data(session: AsyncSession):
    bank1 = BankConfig(
        bank_code="CTBC", bank_name="中國信託", gmail_filter="from:ctbc"
    )
    bank2 = BankConfig(
        bank_code="ESUN", bank_name="玉山銀行", gmail_filter="from:esun"
    )
    session.add_all([bank1, bank2])

    # 2026-03
    bill1 = Bill(
        bank_code="CTBC",
        billing_month="2026-03",
        total_amount=10000,
        due_date=date(2026, 4, 15),
    )
    bill2 = Bill(
        bank_code="ESUN",
        billing_month="2026-03",
        total_amount=5000,
        due_date=date(2026, 4, 20),
    )
    # 2026-02
    bill3 = Bill(
        bank_code="CTBC",
        billing_month="2026-02",
        total_amount=8000,
        due_date=date(2026, 3, 15),
    )
    session.add_all([bill1, bill2, bill3])
    await session.flush()

    txns = [
        Transaction(
            bill_id=bill1.id,
            trans_date=date(2026, 3, 1),
            merchant="星巴克",
            amount=6000,
            category="餐飲",
        ),
        Transaction(
            bill_id=bill1.id,
            trans_date=date(2026, 3, 5),
            merchant="全聯",
            amount=4000,
            category="日用",
        ),
        Transaction(
            bill_id=bill2.id,
            trans_date=date(2026, 3, 10),
            merchant="Amazon",
            amount=5000,
            category="購物",
        ),
    ]
    session.add_all(txns)
    await session.commit()


async def test_trend(client: AsyncClient, db_session: AsyncSession):
    """回傳最近 N 月趨勢。"""
    await _seed_analytics_data(db_session)

    response = await client.get(
        "/api/analytics/trend?months=6", headers=auth_headers()
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 6
    # 確認有 month 和 total 欄位
    months = [item["month"] for item in data]
    assert "2026-03" in months


async def test_categories(client: AsyncClient, db_session: AsyncSession):
    """回傳指定月份的類別分布。"""
    await _seed_analytics_data(db_session)

    response = await client.get(
        "/api/analytics/categories?month=2026-03", headers=auth_headers()
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 3
    categories = {item["category"]: item["total"] for item in data}
    assert categories["餐飲"] == 6000
    assert categories["購物"] == 5000
    assert categories["日用"] == 4000


async def test_banks(client: AsyncClient, db_session: AsyncSession):
    """回傳指定月份按銀行彙總。"""
    await _seed_analytics_data(db_session)

    response = await client.get(
        "/api/analytics/banks?month=2026-03", headers=auth_headers()
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 2
    banks = {item["bank_code"]: item for item in data}
    assert banks["CTBC"]["total"] == 10000
    assert banks["CTBC"]["bank_name"] == "中國信託"
    assert banks["ESUN"]["total"] == 5000
