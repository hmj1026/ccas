"""Bills API 測試（帳單列表、狀態更新、PDF 下載）。"""

import tempfile
from datetime import date
from pathlib import Path

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.storage.models import BankConfig, Bill
from tests.integration.conftest import auth_headers


async def _seed_bills(session: AsyncSession) -> tuple[int, int]:
    """建立測試帳單，回傳 (unpaid_id, paid_id)。"""
    bank = BankConfig(
        bank_code="CTBC", bank_name="中國信託", gmail_filter="from:ctbc"
    )
    session.add(bank)

    bill1 = Bill(
        bank_code="CTBC",
        billing_month="2026-03",
        total_amount=10000,
        due_date=date(2026, 4, 15),
        is_paid=False,
    )
    bill2 = Bill(
        bank_code="CTBC",
        billing_month="2026-02",
        total_amount=8000,
        due_date=date(2026, 3, 15),
        is_paid=True,
    )
    session.add_all([bill1, bill2])
    await session.commit()
    return bill1.id, bill2.id


async def test_list_bills_all(client: AsyncClient, db_session: AsyncSession):
    """查詢全部帳單。"""
    await _seed_bills(db_session)

    response = await client.get(
        "/api/bills?month=2026-03", headers=auth_headers()
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["bank_code"] == "CTBC"


async def test_list_bills_unpaid(client: AsyncClient, db_session: AsyncSession):
    """篩選未繳帳單。"""
    await _seed_bills(db_session)

    response = await client.get(
        "/api/bills?month=2026-03&status=unpaid", headers=auth_headers()
    )
    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["is_paid"] is False


async def test_list_bills_paid(client: AsyncClient, db_session: AsyncSession):
    """篩選已繳帳單。"""
    await _seed_bills(db_session)

    response = await client.get(
        "/api/bills?month=2026-03&status=paid", headers=auth_headers()
    )
    data = response.json()["data"]
    assert len(data) == 0  # 2026-03 only has unpaid


async def test_update_bill_paid(client: AsyncClient, db_session: AsyncSession):
    """將帳單標記為已繳。"""
    unpaid_id, _ = await _seed_bills(db_session)

    response = await client.patch(
        f"/api/bills/{unpaid_id}",
        json={"is_paid": True},
        headers=auth_headers(),
    )
    assert response.status_code == 200
    assert response.json()["data"]["is_paid"] is True


async def test_update_bill_not_found(client: AsyncClient, db_session: AsyncSession):
    """更新不存在的帳單回傳 404。"""
    response = await client.patch(
        "/api/bills/999",
        json={"is_paid": True},
        headers=auth_headers(),
    )
    assert response.status_code == 404


async def test_bill_pdf_url_present(client: AsyncClient, db_session: AsyncSession):
    """帳單有 file_path 時回應包含 pdf_url。"""
    bank = BankConfig(
        bank_code="CTBC", bank_name="中國信託", gmail_filter="from:ctbc"
    )
    session = db_session
    session.add(bank)

    bill = Bill(
        bank_code="CTBC",
        billing_month="2026-03",
        total_amount=5000,
        due_date=date(2026, 4, 15),
        file_path="/tmp/test.pdf",
    )
    session.add(bill)
    await session.commit()

    response = await client.get(
        "/api/bills?month=2026-03", headers=auth_headers()
    )
    data = response.json()["data"]
    assert data[0]["pdf_url"] == f"/api/bills/{bill.id}/pdf"


async def test_bill_pdf_url_null_when_no_file(
    client: AsyncClient, db_session: AsyncSession
):
    """帳單無 file_path 時 pdf_url 為 null。"""
    bank = BankConfig(
        bank_code="CTBC", bank_name="中國信託", gmail_filter="from:ctbc"
    )
    db_session.add(bank)
    bill = Bill(
        bank_code="CTBC",
        billing_month="2026-03",
        total_amount=5000,
        due_date=date(2026, 4, 15),
    )
    db_session.add(bill)
    await db_session.commit()

    response = await client.get(
        "/api/bills?month=2026-03", headers=auth_headers()
    )
    data = response.json()["data"]
    assert data[0]["pdf_url"] is None


async def test_download_pdf_success(client: AsyncClient, db_session: AsyncSession):
    """成功下載帳單 PDF。"""
    # 建立暫存 PDF 檔案
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(b"%PDF-1.4 test content")
        pdf_path = f.name

    try:
        bill = Bill(
            bank_code="CTBC",
            billing_month="2026-03",
            total_amount=5000,
            due_date=date(2026, 4, 15),
            file_path=pdf_path,
        )
        db_session.add(bill)
        await db_session.commit()

        response = await client.get(
            f"/api/bills/{bill.id}/pdf", headers=auth_headers()
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
    finally:
        Path(pdf_path).unlink(missing_ok=True)


async def test_download_pdf_bill_not_found(
    client: AsyncClient, db_session: AsyncSession
):
    """帳單不存在時回傳 404。"""
    response = await client.get("/api/bills/999/pdf", headers=auth_headers())
    assert response.status_code == 404


async def test_download_pdf_file_missing(
    client: AsyncClient, db_session: AsyncSession
):
    """帳單存在但 PDF 檔案遺失時回傳 404。"""
    bill = Bill(
        bank_code="CTBC",
        billing_month="2026-03",
        total_amount=5000,
        due_date=date(2026, 4, 15),
        file_path="/nonexistent/path/bill.pdf",
    )
    db_session.add(bill)
    await db_session.commit()

    response = await client.get(
        f"/api/bills/{bill.id}/pdf", headers=auth_headers()
    )
    assert response.status_code == 404
