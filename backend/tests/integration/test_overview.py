"""Overview API 測試。"""

from datetime import date, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.storage.models import BankConfig, Bill
from tests.integration.conftest import auth_headers


async def _seed_data(session: AsyncSession, month: str = "2026-03"):
    """建立測試資料。"""
    bank = BankConfig(
        bank_code="CTBC", bank_name="中國信託", gmail_filter="from:ctbc"
    )
    session.add(bank)

    bill1 = Bill(
        bank_code="CTBC",
        billing_month=month,
        total_amount=10000,
        due_date=date.today() + timedelta(days=3),
        is_paid=False,
    )
    bill2 = Bill(
        bank_code="ESUN",
        billing_month=month,
        total_amount=5000,
        due_date=date.today() + timedelta(days=30),
        is_paid=True,
    )
    session.add_all([bill1, bill2])
    await session.commit()


async def test_overview_default_month(
    client: AsyncClient, db_session: AsyncSession
):
    """未指定月份時回傳當月摘要。"""
    current_month = date.today().strftime("%Y-%m")
    await _seed_data(db_session, current_month)

    response = await client.get("/api/overview", headers=auth_headers())
    assert response.status_code == 200

    data = response.json()["data"]
    assert data["month"] == current_month
    assert data["total_spending"] == 15000
    assert data["total_paid"] == 5000
    assert data["total_unpaid"] == 10000


async def test_overview_specified_month(
    client: AsyncClient, db_session: AsyncSession
):
    """指定月份時回傳該月份摘要。"""
    await _seed_data(db_session, "2026-01")

    response = await client.get(
        "/api/overview?month=2026-01", headers=auth_headers()
    )
    assert response.status_code == 200
    assert response.json()["data"]["month"] == "2026-01"
    assert response.json()["data"]["total_spending"] == 15000


async def test_overview_upcoming_bills(
    client: AsyncClient, db_session: AsyncSession
):
    """摘要包含即將到期的未繳帳單。"""
    current_month = date.today().strftime("%Y-%m")
    await _seed_data(db_session, current_month)

    response = await client.get("/api/overview", headers=auth_headers())
    data = response.json()["data"]
    upcoming = data["upcoming_bills"]
    # bill1 到期日在 3 天後且未繳，應該出現
    assert len(upcoming) >= 1
    assert upcoming[0]["bank_code"] == "CTBC"
    assert upcoming[0]["is_paid"] is False
