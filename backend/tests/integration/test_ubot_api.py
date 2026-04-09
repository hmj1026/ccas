"""UBOT API integration tests (bills & transactions)."""

from datetime import date

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.storage.models import BankConfig, Bill, Transaction
from tests.integration.conftest import auth_headers


def _make_ubot_bank_config() -> BankConfig:
    return BankConfig(bank_code="UBOT", bank_name="聯邦銀行", gmail_filter="from:ubot")


async def _seed_ubot_data(session: AsyncSession) -> int:
    """Seed UBOT BankConfig + Bill + Transactions. Returns bill id."""
    session.add(_make_ubot_bank_config())

    bill = Bill(
        bank_code="UBOT",
        billing_month="2026-03",
        total_amount=6530,
        due_date=date(2026, 4, 18),
        is_paid=False,
    )
    session.add(bill)
    await session.flush()

    txns = [
        Transaction(
            bill_id=bill.id,
            trans_date=date(2026, 3, 5),
            merchant="7-ELEVEN",
            amount=120,
            currency="TWD",
        ),
        Transaction(
            bill_id=bill.id,
            trans_date=date(2026, 3, 12),
            merchant="全聯福利中心",
            amount=1850,
            currency="TWD",
        ),
        Transaction(
            bill_id=bill.id,
            trans_date=date(2026, 3, 20),
            merchant="PChome線上購物",
            amount=3200,
            currency="TWD",
        ),
    ]
    session.add_all(txns)
    await session.commit()
    return bill.id


async def test_list_bills_ubot_filter(client: AsyncClient, db_session: AsyncSession):
    """bank_code=UBOT filter returns only UBOT bills."""
    await _seed_ubot_data(db_session)

    response = await client.get("/api/bills?bank_code=UBOT", headers=auth_headers())
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["bank_code"] == "UBOT"
    assert data[0]["billing_month"] == "2026-03"
    assert data[0]["total_amount"] == 6530


async def test_list_transactions_ubot(client: AsyncClient, db_session: AsyncSession):
    """UBOT transactions are returned via transactions API."""
    await _seed_ubot_data(db_session)

    response = await client.get(
        "/api/transactions?month=2026-03", headers=auth_headers()
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 3
    merchants = {item["merchant"] for item in data}
    assert merchants == {"7-ELEVEN", "全聯福利中心", "PChome線上購物"}
