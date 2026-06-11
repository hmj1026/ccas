"""Staged Attachments API 整合測試。

驗證：
- 未認證拒絕（401）
- status 逗號過濾（fetch_expired / failed / parse_failed）
- bank_code 過濾
- 排序為 message_date DESC, id DESC
- 回應不含內部欄位（staged_path / gmail_attachment_id / gmail_part_id）
"""

from __future__ import annotations

from datetime import datetime

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.storage.models import BankConfig, StagedAttachment
from tests.integration.conftest import auth_headers


async def _seed_attachments(session: AsyncSession) -> None:
    session.add(
        BankConfig(bank_code="FUBON", bank_name="富邦", gmail_filter="from:fubon")
    )
    session.add(
        BankConfig(bank_code="CTBC", bank_name="中國信託", gmail_filter="from:ctbc")
    )

    session.add_all(
        [
            StagedAttachment(
                bank_code="FUBON",
                gmail_message_id="m-fubon-expired",
                gmail_attachment_id="a-1",
                message_date=datetime(2026, 3, 15),
                original_filename="fubon-2026-03.pdf",
                staged_path=None,
                status="fetch_expired",
                error_reason="fetch_expired: 富邦 email 下載連結已失效",
                source_type="web_fetch",
            ),
            StagedAttachment(
                bank_code="FUBON",
                gmail_message_id="m-fubon-parsed",
                gmail_attachment_id="a-2",
                message_date=datetime(2026, 4, 1),
                original_filename="fubon-2026-04.pdf",
                staged_path="/data/staging/FUBON/ok.pdf",
                status="parsed",
                error_reason=None,
                source_type="web_fetch",
            ),
            StagedAttachment(
                bank_code="CTBC",
                gmail_message_id="m-ctbc-failed",
                gmail_attachment_id="a-3",
                message_date=datetime(2026, 2, 20),
                original_filename="ctbc-2026-02.pdf",
                staged_path=None,
                status="failed",
                error_reason="download_error",
                source_type="attachment",
            ),
            StagedAttachment(
                bank_code="CTBC",
                gmail_message_id="m-ctbc-parsefail",
                gmail_attachment_id="a-4",
                message_date=datetime(2026, 3, 20),
                original_filename="ctbc-2026-03.pdf",
                staged_path=None,
                status="parse_failed",
                error_reason="ParseError: unexpected format",
                source_type="attachment",
            ),
            StagedAttachment(
                bank_code="FUBON",
                gmail_message_id="m-fubon-decryptfail",
                gmail_attachment_id="a-5",
                message_date=datetime(2026, 4, 10),
                original_filename="fubon-2026-04b.pdf",
                staged_path="/data/staging/FUBON/locked.pdf",
                status="decrypt_failed",
                error_reason="DecryptError: no password matched",
                source_type="attachment",
            ),
            StagedAttachment(
                bank_code="FUBON",
                gmail_message_id="m-fubon-manual",
                gmail_attachment_id="a-6",
                message_date=datetime(2026, 4, 15),
                original_filename="fubon-2026-04c.pdf",
                staged_path="/data/staging/FUBON/manual.pdf",
                status="manual_review_needed",
                error_reason="stuck in decrypted over retention window",
                source_type="attachment",
            ),
        ]
    )
    await session.commit()


async def test_requires_auth(client: AsyncClient, db_session: AsyncSession):
    await _seed_attachments(db_session)
    resp = await client.get("/api/staged-attachments")
    assert resp.status_code == 401


async def test_list_all_sorted_by_date_desc(
    client: AsyncClient, db_session: AsyncSession
):
    await _seed_attachments(db_session)
    resp = await client.get("/api/staged-attachments", headers=auth_headers())
    assert resp.status_code == 200
    payload = resp.json()
    data = payload["data"]
    assert payload["pagination"]["total"] == 6
    # 最新 message_date 在前
    dates = [item["message_date"] for item in data]
    assert dates == sorted(dates, reverse=True)


async def test_status_filter_csv(client: AsyncClient, db_session: AsyncSession):
    await _seed_attachments(db_session)
    resp = await client.get(
        "/api/staged-attachments?status=fetch_expired,failed,parse_failed",
        headers=auth_headers(),
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    statuses = {item["status"] for item in data}
    assert statuses == {"fetch_expired", "failed", "parse_failed"}
    # parsed 不應出現
    assert all(item["status"] != "parsed" for item in data)


async def test_status_filter_single(client: AsyncClient, db_session: AsyncSession):
    await _seed_attachments(db_session)
    resp = await client.get(
        "/api/staged-attachments?status=fetch_expired", headers=auth_headers()
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 1
    assert data[0]["status"] == "fetch_expired"
    assert data[0]["bank_code"] == "FUBON"
    assert data[0]["bank_name"] == "富邦"


async def test_status_filter_decrypt_failed_and_manual_review(
    client: AsyncClient, db_session: AsyncSession
):
    """先前缺漏的兩個 status（decrypt_failed / manual_review_needed）應可過濾。"""
    await _seed_attachments(db_session)
    resp = await client.get(
        "/api/staged-attachments?status=decrypt_failed,manual_review_needed",
        headers=auth_headers(),
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["pagination"]["total"] == 2
    statuses = {item["status"] for item in payload["data"]}
    assert statuses == {"decrypt_failed", "manual_review_needed"}


async def test_bank_code_filter(client: AsyncClient, db_session: AsyncSession):
    await _seed_attachments(db_session)
    resp = await client.get(
        "/api/staged-attachments?bank_code=CTBC", headers=auth_headers()
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 2
    assert all(item["bank_code"] == "CTBC" for item in data)


async def test_response_excludes_internal_fields(
    client: AsyncClient, db_session: AsyncSession
):
    await _seed_attachments(db_session)
    resp = await client.get(
        "/api/staged-attachments?status=fetch_expired", headers=auth_headers()
    )
    assert resp.status_code == 200
    item = resp.json()["data"][0]
    # 不應洩漏檔案系統路徑 / Gmail 內部識別
    assert "staged_path" not in item
    assert "gmail_attachment_id" not in item
    assert "gmail_part_id" not in item
    assert "gmail_message_id" not in item


async def test_invalid_status_silently_ignored(
    client: AsyncClient, db_session: AsyncSession
):
    """不在白名單的 status 值應被忽略（視為沒指定該 token），不丟錯。

    設計決策：單一使用者自託管場景，API 的容錯性優先於嚴格驗證；
    若未來此 API 要開放給外部 client 使用，應改為 422 並同時更新本測試。
    """
    await _seed_attachments(db_session)
    resp = await client.get(
        "/api/staged-attachments?status=not_a_real_status",
        headers=auth_headers(),
    )
    assert resp.status_code == 200
    # 全部狀態皆非 not_a_real_status，實際條件為空 → 回傳全部
    assert resp.json()["pagination"]["total"] == 6
