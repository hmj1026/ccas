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


async def _seed_multi_month_transactions(session: AsyncSession):
    """建立跨月帳單與交易，用於無月份篩選測試。"""
    bill_feb = Bill(
        bank_code="CTBC",
        billing_month="2026-02",
        total_amount=1000,
        due_date=date(2026, 3, 15),
    )
    bill_mar = Bill(
        bank_code="CTBC",
        billing_month="2026-03",
        total_amount=2000,
        due_date=date(2026, 4, 15),
    )
    session.add_all([bill_feb, bill_mar])
    await session.flush()

    session.add_all(
        [
            Transaction(
                bill_id=bill_feb.id,
                trans_date=date(2026, 2, 10),
                merchant="全聯",
                amount=500,
                currency="TWD",
            ),
            Transaction(
                bill_id=bill_mar.id,
                trans_date=date(2026, 3, 5),
                merchant="星巴克",
                amount=200,
                currency="TWD",
            ),
        ]
    )
    await session.commit()


async def test_list_transactions_year_filter(
    client: AsyncClient, db_session: AsyncSession
):
    """year 篩選應只回傳該年度交易。"""
    await _seed_multi_month_transactions(db_session)

    response = await client.get("/api/transactions?year=2026", headers=auth_headers())
    assert response.status_code == 200
    body = response.json()
    assert body["pagination"]["total"] == 2
    assert all(item["billing_month"].startswith("2026-") for item in body["data"])


async def test_list_transactions_no_month_returns_all(
    client: AsyncClient, db_session: AsyncSession
):
    """省略 month 參數應回傳所有月份的交易。"""
    await _seed_multi_month_transactions(db_session)

    response = await client.get("/api/transactions", headers=auth_headers())
    assert response.status_code == 200
    body = response.json()
    assert body["pagination"]["total"] == 2
    months = {item["billing_month"] for item in body["data"]}
    assert months == {"2026-02", "2026-03"}


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


async def test_list_transactions_search(client: AsyncClient, db_session: AsyncSession):
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


# Legacy CSV export tests removed; the new endpoint and its coverage live in
# tests/integration/test_exports_router.py (bills-management-and-insights §8).


async def test_list_transactions_filter_by_bank_code(
    client: AsyncClient, db_session: AsyncSession
):
    """bank_code 篩選只回傳該銀行交易（user-guide §7 API）。"""
    bill_ctbc = Bill(
        bank_code="CTBC",
        billing_month="2026-03",
        total_amount=200,
        due_date=date(2026, 4, 15),
    )
    bill_esun = Bill(
        bank_code="ESUN",
        billing_month="2026-03",
        total_amount=300,
        due_date=date(2026, 4, 20),
    )
    db_session.add_all([bill_ctbc, bill_esun])
    await db_session.flush()

    db_session.add_all(
        [
            Transaction(
                bill_id=bill_ctbc.id,
                trans_date=date(2026, 3, 1),
                merchant="星巴克",
                amount=200,
                currency="TWD",
            ),
            Transaction(
                bill_id=bill_esun.id,
                trans_date=date(2026, 3, 2),
                merchant="麥當勞",
                amount=300,
                currency="TWD",
            ),
        ]
    )
    await db_session.commit()

    response = await client.get(
        "/api/transactions?bank_code=CTBC", headers=auth_headers()
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["merchant"] == "星巴克"


async def test_invalid_month_format(client: AsyncClient, db_session: AsyncSession):
    """無效月份格式回傳 422。"""
    response = await client.get(
        "/api/transactions?month=2026-13", headers=auth_headers()
    )
    assert response.status_code == 422
