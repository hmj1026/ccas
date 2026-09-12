"""REST adapters for the agent bill and pipeline aggregate queries."""

from datetime import date, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.storage.models import (
    BankConfig,
    Bill,
    PipelineRun,
    PipelineRunStatus,
    PipelineRunTerminalReason,
    Transaction,
)
from tests.integration.conftest import TEST_TOKEN, auth_headers

AGGREGATE_PATHS = ("/api/bills/payment-due", "/api/pipeline/status")


async def _seed_payment_due(session: AsyncSession) -> tuple[int, int]:
    """建立一組包含已繳、未繳及卡號彙總資料的帳單。"""
    session.add_all(
        [
            BankConfig(
                bank_code="CTBC",
                bank_name="中國信託",
                gmail_filter="from:ctbc",
            ),
            BankConfig(
                bank_code="ESUN",
                bank_name="玉山銀行",
                gmail_filter="from:esun",
            ),
            BankConfig(
                bank_code="FUBON",
                bank_name="台北富邦",
                gmail_filter="from:fubon",
            ),
        ]
    )
    due_later = Bill(
        bank_code="CTBC",
        billing_month="2026-03",
        total_amount=1234,
        due_date=date(2026, 4, 20),
        is_paid=False,
        file_path="/private/statements/ctbc-2026-03.pdf",
    )
    due_soon = Bill(
        bank_code="ESUN",
        billing_month="2026-02",
        total_amount=800,
        due_date=date(2026, 4, 5),
        is_paid=False,
    )
    paid = Bill(
        bank_code="FUBON",
        billing_month="2026-01",
        total_amount=999,
        due_date=date(2026, 4, 1),
        is_paid=True,
    )
    session.add_all([due_later, due_soon, paid])
    await session.flush()
    session.add_all(
        [
            Transaction(
                bill_id=due_later.id,
                trans_date=date(2026, 3, 1),
                merchant="Coffee shop",
                amount=100,
                currency="TWD",
                card_last4="5678",
            ),
            Transaction(
                bill_id=due_later.id,
                trans_date=date(2026, 3, 2),
                merchant="Grocery",
                amount=200,
                currency="TWD",
                card_last4="1234",
            ),
            Transaction(
                bill_id=due_later.id,
                trans_date=date(2026, 3, 3),
                merchant="Transit",
                amount=50,
                currency="TWD",
                card_last4="1234",
            ),
        ]
    )
    await session.commit()
    return due_soon.id, due_later.id


def _pipeline_run(
    run_id: str,
    created_at: datetime,
    *,
    status: PipelineRunStatus = PipelineRunStatus.SUCCEEDED,
    terminal_reason: PipelineRunTerminalReason | None = None,
) -> PipelineRun:
    """建立可供 latest/status 聚合測試使用的 pipeline row。"""
    run = PipelineRun(
        id=run_id,
        job_id=f"job-{run_id}",
        status=status,
        triggered_by="api",
        params={"force": False},
        current_stage="parse",
        current_stage_processed=3,
        current_stage_total=4,
        stage_summary=[
            {
                "stage": "parse",
                "ok": 3,
                "fail": 0,
                "elapsed_ms": 12,
                "counts": {"parsed": 3},
                "errors": [],
            }
        ],
        error_message=None,
        created_at=created_at,
    )
    run.terminal_reason = terminal_reason
    return run


async def test_payment_due_returns_unpaid_agent_bills_in_due_order(
    client: AsyncClient, db_session: AsyncSession
):
    """到期彙總回傳 AgentBill、只含未繳且金額使用 TWD money object。"""
    due_soon_id, due_later_id = await _seed_payment_due(db_session)

    response = await client.get("/api/bills/payment-due", headers=auth_headers())

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert set(body) == {"success", "data", "message"}
    assert [item["id"] for item in body["data"]] == [due_soon_id, due_later_id]
    assert body["data"][0]["due_date"] == "2026-04-05"
    assert body["data"][0]["total_amount"] == {
        "currency": "TWD",
        "value": "800",
    }
    assert body["data"][0]["is_paid"] is False
    assert body["data"][1]["card_last4s"] == ["1234", "5678"]
    assert body["data"][1]["reconciliation_key"] == "CTBC:2026-03:1234,5678"
    assert all(item["is_paid"] is False for item in body["data"])
    assert all(
        "pdf_url" not in item and "file_path" not in item for item in body["data"]
    )


async def test_payment_due_accepts_valid_session_cookie(
    client: AsyncClient, db_session: AsyncSession
):
    """到期彙總沿用既有 session cookie 認證。"""
    await _seed_payment_due(db_session)
    login = await client.post("/api/auth/session", json={"token": TEST_TOKEN})
    assert login.status_code == 204

    response = await client.get("/api/bills/payment-due")

    assert response.status_code == 200
    assert response.json()["success"] is True


@pytest.mark.parametrize("path", AGGREGATE_PATHS)
async def test_aggregate_endpoints_reject_missing_auth(client: AsyncClient, path: str):
    """聚合端點沒有 Bearer 或 session 時回傳 401。"""
    response = await client.get(path)

    assert response.status_code == 401


@pytest.mark.parametrize("path", AGGREGATE_PATHS)
async def test_aggregate_endpoints_reject_invalid_auth(client: AsyncClient, path: str):
    """聚合端點收到無效 Bearer 時回傳 401。"""
    response = await client.get(path, headers=auth_headers("wrong-token"))

    assert response.status_code == 401


async def test_pipeline_status_returns_latest_run_and_needs_human(
    client: AsyncClient, db_session: AsyncSession
):
    """pipeline status 依 created_at、id tie-break，並標示耗盡重試的失敗。"""
    created_at = datetime(2026, 4, 1, 12, 0, 0)
    db_session.add_all(
        [
            _pipeline_run("run-old", created_at),
            _pipeline_run("run-a", created_at + timedelta(days=1)),
            _pipeline_run(
                "run-z",
                created_at + timedelta(days=1),
                status=PipelineRunStatus.FAILED,
                terminal_reason=PipelineRunTerminalReason.RETRIES_EXHAUSTED,
            ),
        ]
    )
    await db_session.commit()

    response = await client.get("/api/pipeline/status", headers=auth_headers())

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    status = body["data"]
    assert status["id"] == "run-z"
    assert status["status"] == "failed"
    assert status["needs_human"] is True
    assert status["stage_summary"][0]["stage"] == "parse"
    assert "terminal_reason" not in status


async def test_pipeline_status_needs_human_requires_retries_exhausted(
    client: AsyncClient, db_session: AsyncSession
):
    """一般 failed 終止原因不可被誤標成 needs_human。"""
    db_session.add(
        _pipeline_run(
            "run-stage-failure",
            datetime(2026, 4, 2, 12, 0, 0),
            status=PipelineRunStatus.FAILED,
            terminal_reason=PipelineRunTerminalReason.STAGE_FAILURE,
        )
    )
    await db_session.commit()

    response = await client.get("/api/pipeline/status", headers=auth_headers())

    assert response.status_code == 200
    assert response.json()["data"]["needs_human"] is False


async def test_pipeline_status_without_runs_returns_404_envelope(
    client: AsyncClient,
):
    """沒有任何執行紀錄時使用既有 404 error envelope。"""
    response = await client.get("/api/pipeline/status", headers=auth_headers())

    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False
    assert body["data"] is None
    assert body["message"]


async def test_existing_bill_list_preserves_rest_money_and_pdf_href(
    client: AsyncClient, db_session: AsyncSession
):
    """新增 Agent adapter 不得改變既有 REST list 的 integer/pdf 相容形狀。"""
    db_session.add(
        BankConfig(
            bank_code="CTBC",
            bank_name="中國信託",
            gmail_filter="from:ctbc",
        )
    )
    bill = Bill(
        bank_code="CTBC",
        billing_month="2026-03",
        total_amount=5000,
        due_date=date(2026, 4, 15),
        file_path="/private/statements/ctbc-2026-03.pdf",
    )
    db_session.add(bill)
    await db_session.commit()

    response = await client.get("/api/bills?month=2026-03", headers=auth_headers())

    assert response.status_code == 200
    item = response.json()["data"][0]
    assert item["total_amount"] == 5000
    assert "currency" not in item
    assert item["pdf_url"] == f"/api/bills/{bill.id}/pdf"
