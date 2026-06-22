"""Bills API 測試（帳單列表、狀態更新、PDF 下載）。"""

import os
import tempfile
from datetime import date
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.storage.models import Bill
from tests.integration.conftest import auth_headers, make_ctbc_bank_config


async def _seed_bills(session: AsyncSession) -> tuple[int, int]:
    """建立測試帳單，回傳 (unpaid_id, paid_id)。"""
    bank = make_ctbc_bank_config()
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


async def test_list_bills_year_filter(client: AsyncClient, db_session: AsyncSession):
    """year 篩選應只回傳該年度帳單。"""
    await _seed_bills(db_session)

    response = await client.get("/api/bills?year=2026", headers=auth_headers())
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 2
    assert all(b["billing_month"].startswith("2026-") for b in data)


async def test_list_bills_bank_filter(client: AsyncClient, db_session: AsyncSession):
    """bank_code 篩選應只回傳該銀行帳單。"""
    await _seed_bills(db_session)

    response = await client.get("/api/bills?bank_code=CTBC", headers=auth_headers())
    assert response.status_code == 200
    data = response.json()["data"]
    assert all(b["bank_code"] == "CTBC" for b in data)


async def test_list_bills_no_month_returns_all(
    client: AsyncClient, db_session: AsyncSession
):
    """省略 month 參數應回傳所有帳單（含分頁）。"""
    await _seed_bills(db_session)

    response = await client.get("/api/bills", headers=auth_headers())
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert len(body["data"]) == 2
    assert "pagination" in body
    assert body["pagination"]["total"] == 2
    # 預設依 billing_month desc 排序
    assert body["data"][0]["billing_month"] == "2026-03"
    assert body["data"][1]["billing_month"] == "2026-02"


async def test_list_bills_by_month(client: AsyncClient, db_session: AsyncSession):
    """指定 month 篩選時只回傳該月帳單。"""
    await _seed_bills(db_session)

    response = await client.get("/api/bills?month=2026-03", headers=auth_headers())
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["bank_code"] == "CTBC"
    assert data[0]["billing_month"] == "2026-03"


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
    """篩選已繳帳單：須實際回傳 paid 帳單（非空集合假通過）。"""
    _unpaid_id, paid_id = await _seed_bills(db_session)

    # 2026-02 有一筆 paid 帳單 → status=paid 應回傳它
    response = await client.get(
        "/api/bills?month=2026-02&status=paid", headers=auth_headers()
    )
    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["id"] == paid_id
    assert data[0]["is_paid"] is True

    # 反向：2026-03 僅有 unpaid → status=paid 應為空
    empty = await client.get(
        "/api/bills?month=2026-03&status=paid", headers=auth_headers()
    )
    assert len(empty.json()["data"]) == 0


async def test_list_bills_pagination(client: AsyncClient, db_session: AsyncSession):
    """分頁參數正確分割資料。"""
    bank = make_ctbc_bank_config()
    db_session.add(bank)
    for i in range(1, 6):
        db_session.add(
            Bill(
                bank_code="CTBC",
                billing_month=f"2026-{i:02d}",
                total_amount=i * 1000,
                due_date=date(2026, i, 15),
            )
        )
    await db_session.commit()

    response = await client.get("/api/bills?page=1&page_size=2", headers=auth_headers())
    body = response.json()
    assert len(body["data"]) == 2
    assert body["pagination"]["total"] == 5
    assert body["pagination"]["total_pages"] == 3
    assert body["pagination"]["page"] == 1
    assert body["pagination"]["page_size"] == 2


async def test_bill_transactions_returns_all_and_total_header_when_under_cap(
    client: AsyncClient, db_session: AsyncSession
):
    from ccas.storage.models import Transaction

    unpaid_id, _ = await _seed_bills(db_session)
    db_session.add_all(
        [
            Transaction(
                bill_id=unpaid_id,
                trans_date=date(2026, 3, 1),
                merchant=f"M{i}",
                amount=100,
                currency="TWD",
            )
            for i in range(3)
        ]
    )
    await db_session.commit()

    resp = await client.get(
        f"/api/bills/{unpaid_id}/transactions", headers=auth_headers()
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["data"]) == 3
    assert resp.headers["X-Total-Count"] == "3"
    # 未截斷時 message 留空。
    assert body["message"] == ""


async def test_bill_transactions_capped_at_hard_limit(
    client: AsyncClient, db_session: AsyncSession
):
    """R-api-pagination：交易明細隱式上限，避免異常帳單拖垮回應；完整筆數走 header。"""
    from ccas.api.routers.bills import TRANSACTIONS_HARD_LIMIT
    from ccas.storage.models import Transaction

    unpaid_id, _ = await _seed_bills(db_session)
    total = TRANSACTIONS_HARD_LIMIT + 5
    db_session.add_all(
        [
            Transaction(
                bill_id=unpaid_id,
                trans_date=date(2026, 3, 1),
                merchant=f"M{i}",
                amount=100,
                currency="TWD",
            )
            for i in range(total)
        ]
    )
    await db_session.commit()

    resp = await client.get(
        f"/api/bills/{unpaid_id}/transactions", headers=auth_headers()
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["data"]) == TRANSACTIONS_HARD_LIMIT
    assert resp.headers["X-Total-Count"] == str(total)
    # 截斷時 body 內提供 in-band 提示。
    assert str(total) in body["message"]


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
    bank = make_ctbc_bank_config()
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

    response = await client.get("/api/bills?month=2026-03", headers=auth_headers())
    data = response.json()["data"]
    assert data[0]["pdf_url"] == f"/api/bills/{bill.id}/pdf"


async def test_bill_pdf_url_null_when_no_file(
    client: AsyncClient, db_session: AsyncSession
):
    """帳單無 file_path 時 pdf_url 為 null。"""
    bank = make_ctbc_bank_config()
    db_session.add(bank)
    bill = Bill(
        bank_code="CTBC",
        billing_month="2026-03",
        total_amount=5000,
        due_date=date(2026, 4, 15),
    )
    db_session.add(bill)
    await db_session.commit()

    response = await client.get("/api/bills?month=2026-03", headers=auth_headers())
    data = response.json()["data"]
    assert data[0]["pdf_url"] is None


async def test_download_pdf_success(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
):
    """成功下載帳單 PDF。"""
    from ccas.config import get_settings

    with tempfile.TemporaryDirectory() as tmp_dir:
        pdf_path = Path(tmp_dir) / "test.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 test content")
        monkeypatch.setattr(get_settings(), "staging_dir", tmp_dir)

        bill = Bill(
            bank_code="CTBC",
            billing_month="2026-03",
            total_amount=5000,
            due_date=date(2026, 4, 15),
            file_path=str(pdf_path),
        )
        db_session.add(bill)
        await db_session.commit()

        response = await client.get(f"/api/bills/{bill.id}/pdf", headers=auth_headers())
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"


async def test_download_pdf_bill_not_found(
    client: AsyncClient, db_session: AsyncSession
):
    """帳單不存在時回傳 404。"""
    response = await client.get("/api/bills/999/pdf", headers=auth_headers())
    assert response.status_code == 404


async def test_download_pdf_file_missing(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
):
    """帳單存在但 PDF 檔案遺失時回傳 404。"""
    from ccas.config import get_settings

    with tempfile.TemporaryDirectory() as tmp_dir:
        monkeypatch.setattr(get_settings(), "staging_dir", tmp_dir)

        bill = Bill(
            bank_code="CTBC",
            billing_month="2026-03",
            total_amount=5000,
            due_date=date(2026, 4, 15),
            file_path=os.path.join(tmp_dir, "nonexistent.pdf"),
        )
        db_session.add(bill)
        await db_session.commit()

        response = await client.get(f"/api/bills/{bill.id}/pdf", headers=auth_headers())
        assert response.status_code == 404


async def test_download_pdf_path_outside_staging_root_returns_404(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
):
    """帳單 PDF 路徑不在 staging 根目錄下時，rebase 後檔案不存在應回傳 404。"""
    from ccas.config import get_settings

    with tempfile.TemporaryDirectory() as allowed_dir:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as outside_file:
            outside_file.write(b"%PDF-1.4 outside")
            outside_path = outside_file.name

        monkeypatch.setattr(get_settings(), "staging_dir", allowed_dir)

        try:
            bill = Bill(
                bank_code="CTBC",
                billing_month="2026-03",
                total_amount=5000,
                due_date=date(2026, 4, 15),
                file_path=outside_path,
            )
            db_session.add(bill)
            await db_session.commit()

            response = await client.get(
                f"/api/bills/{bill.id}/pdf", headers=auth_headers()
            )
            assert response.status_code == 404
        finally:
            Path(outside_path).unlink(missing_ok=True)
