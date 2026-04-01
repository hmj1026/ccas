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


async def test_list_bills_all(client: AsyncClient, db_session: AsyncSession):
    """查詢全部帳單。"""
    await _seed_bills(db_session)

    response = await client.get("/api/bills?month=2026-03", headers=auth_headers())
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

        response = await client.get(
            f"/api/bills/{bill.id}/pdf", headers=auth_headers()
        )
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

        response = await client.get(
            f"/api/bills/{bill.id}/pdf", headers=auth_headers()
        )
        assert response.status_code == 404


async def test_download_pdf_rejects_path_outside_staging_root(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
):
    """帳單 PDF 若不在 staging 根目錄下應拒絕存取。"""
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
            assert response.status_code == 403
        finally:
            Path(outside_path).unlink(missing_ok=True)
