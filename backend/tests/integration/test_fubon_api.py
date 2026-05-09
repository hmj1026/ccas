"""FUBON API integration tests (bills & transactions)."""

from datetime import date

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.storage.models import BankConfig, Bill, Transaction
from tests.integration.conftest import auth_headers


def _make_fubon_bank_config() -> BankConfig:
    return BankConfig(
        bank_code="FUBON", bank_name="台北富邦銀行", gmail_filter="from:fubon"
    )


async def _seed_fubon_data(session: AsyncSession) -> int:
    """Seed FUBON BankConfig + Bill + Transactions. Returns bill id."""
    session.add(_make_fubon_bank_config())

    bill = Bill(
        bank_code="FUBON",
        billing_month="2026-03",
        total_amount=15800,
        due_date=date(2026, 4, 15),
        is_paid=False,
    )
    session.add(bill)
    await session.flush()

    txns = [
        Transaction(
            bill_id=bill.id,
            trans_date=date(2026, 3, 5),
            merchant="全聯福利中心",
            amount=680,
            currency="TWD",
        ),
        Transaction(
            bill_id=bill.id,
            trans_date=date(2026, 3, 10),
            merchant="台灣大哥大",
            amount=499,
            currency="TWD",
        ),
        Transaction(
            bill_id=bill.id,
            trans_date=date(2026, 3, 15),
            merchant="誠品書店",
            amount=1250,
            currency="TWD",
        ),
    ]
    session.add_all(txns)
    await session.commit()
    return bill.id


async def test_list_bills_fubon_filter(client: AsyncClient, db_session: AsyncSession):
    """bank_code=FUBON filter returns only FUBON bills."""
    await _seed_fubon_data(db_session)

    response = await client.get("/api/bills?bank_code=FUBON", headers=auth_headers())
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["bank_code"] == "FUBON"
    assert data[0]["billing_month"] == "2026-03"
    assert data[0]["total_amount"] == 15800


async def test_list_transactions_fubon(client: AsyncClient, db_session: AsyncSession):
    """FUBON transactions are returned via transactions API."""
    await _seed_fubon_data(db_session)

    response = await client.get(
        "/api/transactions?month=2026-03", headers=auth_headers()
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 3
    merchants = {item["merchant"] for item in data}
    assert merchants == {"全聯福利中心", "台灣大哥大", "誠品書店"}
