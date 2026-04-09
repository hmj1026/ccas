"""TAISHIN API integration tests (bills & transactions)."""

from datetime import date

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.storage.models import BankConfig, Bill, Transaction
from tests.integration.conftest import auth_headers


def _make_taishin_bank_config() -> BankConfig:
    return BankConfig(
        bank_code="TAISHIN", bank_name="台新銀行", gmail_filter="from:taishin"
    )


async def _seed_taishin_data(session: AsyncSession) -> int:
    """Seed TAISHIN BankConfig + Bill + Transactions. Returns bill id."""
    session.add(_make_taishin_bank_config())

    bill = Bill(
        bank_code="TAISHIN",
        billing_month="2026-03",
        total_amount=7680,
        due_date=date(2026, 4, 22),
        is_paid=False,
    )
    session.add(bill)
    await session.flush()

    txns = [
        Transaction(
            bill_id=bill.id,
            trans_date=date(2026, 3, 3),
            merchant="全聯福利中心",
            amount=520,
            currency="TWD",
        ),
        Transaction(
            bill_id=bill.id,
            trans_date=date(2026, 3, 10),
            merchant="好市多",
            amount=2360,
            currency="TWD",
        ),
        Transaction(
            bill_id=bill.id,
            trans_date=date(2026, 3, 18),
            merchant="NETFLIX.COM",
            amount=390,
            currency="TWD",
        ),
    ]
    session.add_all(txns)
    await session.commit()
    return bill.id


async def test_list_bills_taishin_filter(client: AsyncClient, db_session: AsyncSession):
    """bank_code=TAISHIN filter returns only TAISHIN bills."""
    await _seed_taishin_data(db_session)

    response = await client.get("/api/bills?bank_code=TAISHIN", headers=auth_headers())
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["bank_code"] == "TAISHIN"
    assert data[0]["billing_month"] == "2026-03"
    assert data[0]["total_amount"] == 7680


async def test_list_transactions_taishin(client: AsyncClient, db_session: AsyncSession):
    """TAISHIN transactions are returned via transactions API."""
    await _seed_taishin_data(db_session)

    response = await client.get(
        "/api/transactions?month=2026-03", headers=auth_headers()
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 3
    merchants = {item["merchant"] for item in data}
    assert merchants == {"全聯福利中心", "好市多", "NETFLIX.COM"}
