"""ESUN bank_code filtering tests for bills and transactions API."""

from datetime import date

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.storage.models import BankConfig, Bill, Transaction
from tests.integration.conftest import auth_headers


def _make_esun_bank_config() -> BankConfig:
    """Create ESUN test BankConfig."""
    return BankConfig(bank_code="ESUN", bank_name="玉山銀行", gmail_filter="from:esun")


async def _seed_esun_data(session: AsyncSession) -> None:
    """Seed ESUN BankConfig + Bill + Transactions."""
    session.add(_make_esun_bank_config())

    bill = Bill(
        bank_code="ESUN",
        billing_month="2026-03",
        total_amount=1880,
        due_date=date(2026, 4, 15),
        is_paid=False,
    )
    session.add(bill)
    await session.flush()

    txns = [
        Transaction(
            bill_id=bill.id,
            trans_date=date(2026, 3, 1),
            merchant="全家便利商店",
            amount=350,
            currency="TWD",
        ),
        Transaction(
            bill_id=bill.id,
            trans_date=date(2026, 3, 8),
            merchant="蝦皮購物",
            amount=1280,
            currency="TWD",
        ),
        Transaction(
            bill_id=bill.id,
            trans_date=date(2026, 3, 15),
            merchant="星巴克",
            amount=250,
            currency="TWD",
        ),
    ]
    session.add_all(txns)
    await session.commit()


async def test_list_bills_bank_code_esun(client: AsyncClient, db_session: AsyncSession):
    """GET /api/bills?bank_code=ESUN returns ESUN bills."""
    await _seed_esun_data(db_session)

    response = await client.get("/api/bills?bank_code=ESUN", headers=auth_headers())
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["bank_code"] == "ESUN"
    assert data[0]["billing_month"] == "2026-03"
    assert data[0]["total_amount"] == 1880


async def test_list_transactions_bank_code_esun(
    client: AsyncClient, db_session: AsyncSession
):
    """GET /api/transactions?bank_code=ESUN returns ESUN transactions."""
    await _seed_esun_data(db_session)

    response = await client.get(
        "/api/transactions?bank_code=ESUN", headers=auth_headers()
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 3
    merchants = {t["merchant"] for t in data}
    assert merchants == {"全家便利商店", "蝦皮購物", "星巴克"}
