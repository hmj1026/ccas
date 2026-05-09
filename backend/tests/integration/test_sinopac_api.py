"""SINOPAC API integration tests (bills & transactions)."""

from datetime import date

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.storage.models import BankConfig, Bill, Transaction
from tests.integration.conftest import auth_headers


def _make_sinopac_bank_config() -> BankConfig:
    return BankConfig(
        bank_code="SINOPAC", bank_name="永豐銀行", gmail_filter="from:sinopac"
    )


async def _seed_sinopac_data(session: AsyncSession) -> int:
    """Seed SINOPAC BankConfig + Bill + Transactions. Returns bill id."""
    session.add(_make_sinopac_bank_config())

    bill = Bill(
        bank_code="SINOPAC",
        billing_month="2026-03",
        total_amount=8750,
        due_date=date(2026, 4, 20),
        is_paid=False,
    )
    session.add(bill)
    await session.flush()

    txns = [
        Transaction(
            bill_id=bill.id,
            trans_date=date(2026, 3, 1),
            merchant="全聯福利中心",
            amount=420,
            currency="TWD",
        ),
        Transaction(
            bill_id=bill.id,
            trans_date=date(2026, 3, 8),
            merchant="家樂福",
            amount=1280,
            currency="TWD",
        ),
        Transaction(
            bill_id=bill.id,
            trans_date=date(2026, 3, 15),
            merchant="momo購物網",
            amount=2350,
            currency="TWD",
        ),
    ]
    session.add_all(txns)
    await session.commit()
    return bill.id


async def test_list_bills_sinopac_filter(client: AsyncClient, db_session: AsyncSession):
    """bank_code=SINOPAC filter returns only SINOPAC bills."""
    await _seed_sinopac_data(db_session)

    response = await client.get("/api/bills?bank_code=SINOPAC", headers=auth_headers())
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["bank_code"] == "SINOPAC"
    assert data[0]["billing_month"] == "2026-03"
    assert data[0]["total_amount"] == 8750


async def test_list_transactions_sinopac(client: AsyncClient, db_session: AsyncSession):
    """SINOPAC transactions are returned via transactions API."""
    await _seed_sinopac_data(db_session)

    response = await client.get(
        "/api/transactions?month=2026-03", headers=auth_headers()
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 3
    merchants = {item["merchant"] for item in data}
    assert merchants == {"全聯福利中心", "家樂福", "momo購物網"}
