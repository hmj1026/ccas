"""Transactions API 測試（含 CSV 匯出）。"""

from datetime import date

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.storage.models import Bill, Transaction
from tests.integration.conftest import auth_headers


async def _seed_transactions(session: AsyncSession):
    bill = Bill(
        bank_code="CTBC",
        billing_month="2026-03",
        total_amount=5000,
        due_date=date(2026, 4, 15),
        is_paid=False,
    )
    session.add(bill)
    await session.flush()

    txns = [
        Transaction(
            bill_id=bill.id,
            trans_date=date(2026, 3, 1),
            merchant="星巴克",
            amount=200,
            currency="TWD",
            category="餐飲",
        ),
        Transaction(
            bill_id=bill.id,
            trans_date=date(2026, 3, 5),
            merchant="全聯",
            amount=800,
            currency="TWD",
            category="日用",
        ),
        Transaction(
            bill_id=bill.id,
            trans_date=date(2026, 3, 10),
            merchant="Amazon",
            amount=4000,
            currency="TWD",
            category="購物",
        ),
    ]
    session.add_all(txns)
    await session.commit()


async def test_list_transactions(client: AsyncClient, db_session: AsyncSession):
    """查詢交易列表含分頁資訊。"""
    await _seed_transactions(db_session)

    response = await client.get(
        "/api/transactions?month=2026-03", headers=auth_headers()
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert len(body["data"]) == 3
    assert body["pagination"]["total"] == 3
    assert body["pagination"]["page"] == 1


async def test_list_transactions_filter_category(
    client: AsyncClient, db_session: AsyncSession
):
    """以分類過濾交易。"""
    await _seed_transactions(db_session)

    response = await client.get(
        "/api/transactions?month=2026-03&category=餐飲",
        headers=auth_headers(),
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["merchant"] == "星巴克"


async def test_list_transactions_search(
    client: AsyncClient, db_session: AsyncSession
):
    """商家名稱搜尋。"""
    await _seed_transactions(db_session)

    response = await client.get(
        "/api/transactions?month=2026-03&q=Amazon",
        headers=auth_headers(),
    )
    assert response.status_code == 200
    assert len(response.json()["data"]) == 1


async def test_list_transactions_pagination(
    client: AsyncClient, db_session: AsyncSession
):
    """分頁功能。"""
    await _seed_transactions(db_session)

    response = await client.get(
        "/api/transactions?month=2026-03&page=1&page_size=2",
        headers=auth_headers(),
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["data"]) == 2
    assert body["pagination"]["total"] == 3
    assert body["pagination"]["total_pages"] == 2


async def test_export_csv(client: AsyncClient, db_session: AsyncSession):
    """CSV 匯出包含 BOM 與正確欄位。"""
    await _seed_transactions(db_session)

    response = await client.get(
        "/api/transactions/export?month=2026-03",
        headers=auth_headers(),
    )
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "ccas-transactions-2026-03.csv" in response.headers["content-disposition"]

    content = response.content.decode("utf-8-sig")
    lines = content.strip().split("\n")
    # header + 3 data rows
    assert len(lines) == 4
    assert "交易日期" in lines[0]
    assert "商家名稱" in lines[0]


async def test_export_csv_with_bank_code(
    client: AsyncClient, db_session: AsyncSession
):
    """CSV 檔名含 bank_code。"""
    await _seed_transactions(db_session)

    response = await client.get(
        "/api/transactions/export?month=2026-03&bank_code=CTBC",
        headers=auth_headers(),
    )
    assert response.status_code == 200
    assert "ccas-transactions-2026-03-CTBC.csv" in response.headers[
        "content-disposition"
    ]


async def test_invalid_month_format(client: AsyncClient, db_session: AsyncSession):
    """無效月份格式回傳 422。"""
    response = await client.get(
        "/api/transactions?month=2026-13", headers=auth_headers()
    )
    assert response.status_code == 422
