"""CATHAY API integration tests (bills & transactions)."""

from datetime import date

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.storage.models import BankConfig, Bill, Transaction
from tests.integration.conftest import auth_headers


def _make_cathay_bank_config() -> BankConfig:
    return BankConfig(
        bank_code="CATHAY", bank_name="國泰世華銀行", gmail_filter="from:cathay"
    )


async def _seed_cathay_data(session: AsyncSession) -> int:
    """Seed CATHAY BankConfig + Bill + Transactions. Returns bill id."""
    session.add(_make_cathay_bank_config())

    bill = Bill(
        bank_code="CATHAY",
        billing_month="2026-03",
        total_amount=9200,
        due_date=date(2026, 4, 12),
        is_paid=False,
    )
    session.add(bill)
    await session.flush()

    txns = [
        Transaction(
            bill_id=bill.id,
            trans_date=date(2026, 3, 2),
            merchant="全家便利商店",
            amount=180,
            currency="TWD",
        ),
        Transaction(
            bill_id=bill.id,
            trans_date=date(2026, 3, 10),
            merchant="誠品書店",
            amount=1450,
            currency="TWD",
        ),
        Transaction(
            bill_id=bill.id,
            trans_date=date(2026, 3, 18),
            merchant="好市多",
            amount=3200,
            currency="TWD",
        ),
    ]
    session.add_all(txns)
    await session.commit()
    return bill.id


async def test_list_bills_cathay_filter(client: AsyncClient, db_session: AsyncSession):
    """bank_code=CATHAY filter returns only CATHAY bills."""
    await _seed_cathay_data(db_session)

    response = await client.get("/api/bills?bank_code=CATHAY", headers=auth_headers())
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["bank_code"] == "CATHAY"
    assert data[0]["billing_month"] == "2026-03"
    assert data[0]["total_amount"] == 9200


async def test_list_transactions_cathay(client: AsyncClient, db_session: AsyncSession):
    """CATHAY transactions are returned via transactions API."""
    await _seed_cathay_data(db_session)

    response = await client.get(
        "/api/transactions?month=2026-03", headers=auth_headers()
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 3
    merchants = {item["merchant"] for item in data}
    assert merchants == {"全家便利商店", "誠品書店", "好市多"}
