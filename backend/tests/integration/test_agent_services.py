"""Shared Agent query services, exercised without the HTTP transport."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.services.bills import get_bill, get_payment_due, list_bills
from ccas.services.budgets import budget_status
from ccas.services.pipeline import pipeline_status
from ccas.services.schemas import AgentQueryError
from ccas.services.transactions import query_transactions
from ccas.storage.models import (
    BankConfig,
    Bill,
    Budget,
    BudgetScope,
    PipelineRun,
    PipelineRunStatus,
    Transaction,
)


def _dump_projection(projection: Any) -> dict[str, Any]:
    """Assert the common service projection seam and return JSON-mode payload."""
    assert isinstance(projection.rest_metadata, dict)
    return projection.payload.model_dump(mode="json")


def _assert_not_found(error: AgentQueryError) -> None:
    assert error.code == "resource_not_found"
    assert error.message.strip()
    assert error.needs_human is False
    assert error.data is None


async def test_list_bills_projection_omits_paths_and_stabilizes_card_identity(
    db_session: AsyncSession,
):
    db_session.add(
        BankConfig(
            bank_code="CTBC",
            bank_name="中國信託",
            gmail_filter="from:ctbc",
        )
    )
    cards_bill = Bill(
        bank_code="CTBC",
        billing_month="2026-03",
        total_amount=1234,
        due_date=date(2026, 4, 15),
        file_path=None,
        is_paid=False,
    )
    no_card_bill = Bill(
        bank_code="ESUN",
        billing_month="2026-02",
        total_amount=500,
        due_date=date(2026, 3, 20),
        file_path=None,
        is_paid=True,
    )
    db_session.add_all([cards_bill, no_card_bill])
    await db_session.flush()
    db_session.add_all(
        [
            Transaction(
                bill_id=cards_bill.id,
                trans_date=date(2026, 3, 1),
                merchant="Market",
                amount=1000,
                card_last4="5678",
                currency="TWD",
            ),
            Transaction(
                bill_id=cards_bill.id,
                trans_date=date(2026, 3, 2),
                merchant="Cafe",
                amount=234,
                card_last4="1234",
                currency="TWD",
            ),
            Transaction(
                bill_id=cards_bill.id,
                trans_date=date(2026, 3, 3),
                merchant="Cafe",
                amount=0,
                card_last4="1234",
                currency="TWD",
            ),
            Transaction(
                bill_id=no_card_bill.id,
                trans_date=date(2026, 2, 3),
                merchant="Unknown",
                amount=500,
                card_last4=None,
                currency="TWD",
            ),
        ]
    )
    await db_session.commit()

    body = _dump_projection(await list_bills(db_session))

    assert [item["billing_month"] for item in body["data"]] == [
        "2026-03",
        "2026-02",
    ]
    with_cards, without_cards = body["data"]
    assert with_cards["bank_name"] == "中國信託"
    assert with_cards["total_amount"] == {"currency": "TWD", "value": "1234"}
    assert with_cards["card_last4s"] == ["1234", "5678"]
    assert with_cards["reconciliation_key"] == "CTBC:2026-03:1234,5678"
    assert without_cards["card_last4s"] == []
    assert without_cards["reconciliation_key"] == "ESUN:2026-02:due-2026-03-20"
    assert all(
        "pdf_url" not in item and "file_path" not in item for item in body["data"]
    )


async def test_list_bills_month_precedes_year_and_filters_bank_and_status(
    db_session: AsyncSession,
):
    db_session.add_all(
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
        ]
    )
    target = Bill(
        bank_code="CTBC",
        billing_month="2026-03",
        total_amount=100,
        due_date=date(2026, 4, 1),
        is_paid=False,
    )
    year_match_only = Bill(
        bank_code="CTBC",
        billing_month="2025-03",
        total_amount=200,
        due_date=date(2025, 4, 1),
        is_paid=False,
    )
    bank_match_only = Bill(
        bank_code="ESUN",
        billing_month="2026-03",
        total_amount=300,
        due_date=date(2026, 4, 1),
        is_paid=False,
    )
    status_match_only = Bill(
        bank_code="CTBC",
        billing_month="2026-04",
        total_amount=400,
        due_date=date(2026, 5, 1),
        is_paid=True,
    )
    db_session.add_all([target, year_match_only, bank_match_only, status_match_only])
    await db_session.commit()

    body = _dump_projection(
        await list_bills(
            db_session,
            month="2026-03",
            year=2025,
            bank_code="CTBC",
            status="unpaid",
        )
    )

    assert [item["id"] for item in body["data"]] == [target.id]
    assert body["data"][0]["billing_month"] == "2026-03"

    paid_body = _dump_projection(
        await list_bills(
            db_session,
            month="2026-04",
            bank_code="CTBC",
            status="unpaid",
        )
    )
    assert paid_body["data"] == []


async def test_list_bills_empty_page_has_one_total_page_and_no_next_page(
    db_session: AsyncSession,
):
    db_session.add(
        Bill(
            bank_code="CTBC",
            billing_month="2026-03",
            total_amount=100,
            due_date=date(2026, 4, 1),
        )
    )
    await db_session.commit()

    body = _dump_projection(await list_bills(db_session, page=2, page_size=20))

    assert body["data"] == []
    assert body["pagination"] == {
        "page": 2,
        "page_size": 20,
        "total": 1,
        "total_pages": 1,
        "has_next": False,
    }


async def test_get_bill_returns_agent_bill_projection(db_session: AsyncSession):
    bill = Bill(
        bank_code="CTBC",
        billing_month="2026-03",
        total_amount=2500,
        due_date=date(2026, 4, 15),
        is_paid=False,
    )
    db_session.add(bill)
    await db_session.commit()

    body = _dump_projection(await get_bill(db_session, bill.id))

    assert body["data"]["id"] == bill.id
    assert body["data"]["bank_code"] == "CTBC"
    assert body["data"]["total_amount"] == {"currency": "TWD", "value": "2500"}
    assert "pdf_url" not in body["data"]


async def test_get_bill_missing_resource_raises_agent_query_error(
    db_session: AsyncSession,
):
    with pytest.raises(AgentQueryError) as caught:
        await get_bill(db_session, 9999)

    _assert_not_found(caught.value)


async def test_query_transactions_keeps_duplicate_ranks_across_filters_and_pages(
    db_session: AsyncSession,
):
    db_session.add_all(
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
        ]
    )
    first_bill = Bill(
        bank_code="CTBC",
        billing_month="2026-03",
        total_amount=-300,
        due_date=date(2026, 4, 15),
    )
    other_bill = Bill(
        bank_code="ESUN",
        billing_month="2026-03",
        total_amount=-100,
        due_date=date(2026, 4, 20),
    )
    month_excluded_bill = Bill(
        bank_code="FUBON",
        billing_month="2025-03",
        total_amount=999,
        due_date=date(2025, 4, 20),
    )
    db_session.add_all([first_bill, other_bill, month_excluded_bill])
    await db_session.flush()

    first_duplicate = Transaction(
        bill_id=first_bill.id,
        trans_date=date(2026, 3, 10),
        merchant="Cafe",
        amount=-100,
        original_amount=-120,
        card_last4="1111",
        category="keep",
        currency="TWD",
    )
    second_duplicate = Transaction(
        bill_id=first_bill.id,
        trans_date=date(2026, 3, 10),
        merchant="Cafe",
        amount=-100,
        card_last4="1111",
        category="drop",
        currency="TWD",
    )
    third_duplicate = Transaction(
        bill_id=first_bill.id,
        trans_date=date(2026, 3, 10),
        merchant="Cafe",
        amount=-100,
        card_last4="1111",
        category="keep",
        currency="TWD",
    )
    other_bill_transaction = Transaction(
        bill_id=other_bill.id,
        trans_date=date(2026, 3, 10),
        merchant="Cafe",
        amount=-100,
        card_last4="2222",
        category="keep",
        currency="TWD",
    )
    month_excluded_transaction = Transaction(
        bill_id=month_excluded_bill.id,
        trans_date=date(2025, 3, 10),
        merchant="Cafe",
        amount=999,
        card_last4="3333",
        category="keep",
        currency="TWD",
    )
    db_session.add_all(
        [
            first_duplicate,
            second_duplicate,
            third_duplicate,
            other_bill_transaction,
            month_excluded_transaction,
        ]
    )
    await db_session.commit()

    full_body = _dump_projection(
        await query_transactions(
            db_session,
            month="2026-03",
            year=2025,
            sort="trans_date_asc",
            page=1,
            page_size=20,
        )
    )
    by_id = {item["id"]: item for item in full_body["data"]}
    first_key = f"{first_bill.id}:2026-03-10:-100:Cafe"
    other_key = f"{other_bill.id}:2026-03-10:-100:Cafe"
    assert set(by_id) == {
        first_duplicate.id,
        second_duplicate.id,
        third_duplicate.id,
        other_bill_transaction.id,
    }
    assert by_id[first_duplicate.id]["reconciliation_key"] == first_key
    assert by_id[second_duplicate.id]["reconciliation_key"] == f"{first_key}#2"
    assert by_id[third_duplicate.id]["reconciliation_key"] == f"{first_key}#3"
    assert by_id[other_bill_transaction.id]["reconciliation_key"] == other_key
    assert by_id[first_duplicate.id]["amount"] == {
        "currency": "TWD",
        "value": "-100",
    }
    assert by_id[first_duplicate.id]["original_amount"] == {
        "currency": "TWD",
        "value": "-120",
    }

    page_one = _dump_projection(
        await query_transactions(
            db_session,
            month="2026-03",
            year=2025,
            bank_code="CTBC",
            category="keep",
            sort="trans_date_asc",
            page=1,
            page_size=1,
        )
    )
    page_two = _dump_projection(
        await query_transactions(
            db_session,
            month="2026-03",
            year=2025,
            bank_code="CTBC",
            category="keep",
            sort="trans_date_asc",
            page=2,
            page_size=1,
        )
    )
    filtered_items = page_one["data"] + page_two["data"]
    assert {item["id"] for item in filtered_items} == {
        first_duplicate.id,
        third_duplicate.id,
    }
    assert any(
        item["reconciliation_key"] == f"{first_key}#3" for item in filtered_items
    )


async def test_get_payment_due_returns_only_unpaid_bills_in_due_date_order(
    db_session: AsyncSession,
):
    soon = Bill(
        bank_code="CTBC",
        billing_month="2026-03",
        total_amount=100,
        due_date=date(2026, 4, 1),
        is_paid=False,
    )
    later = Bill(
        bank_code="ESUN",
        billing_month="2026-03",
        total_amount=200,
        due_date=date(2026, 4, 20),
        is_paid=False,
    )
    paid = Bill(
        bank_code="FUBON",
        billing_month="2026-03",
        total_amount=300,
        due_date=date(2026, 3, 25),
        is_paid=True,
    )
    db_session.add_all([soon, later, paid])
    await db_session.commit()

    body = _dump_projection(await get_payment_due(db_session))

    assert [item["id"] for item in body["data"]] == [soon.id, later.id]
    assert all(item["is_paid"] is False for item in body["data"])
    assert body["data"][0]["total_amount"] == {
        "currency": "TWD",
        "value": "100",
    }


async def test_budget_status_current_period_is_opt_in(
    db_session: AsyncSession,
):
    today = date.today()
    period = f"{today.year:04d}-{today.month:02d}"
    budget = Budget(
        scope=BudgetScope.MONTHLY_TOTAL,
        scope_ref=None,
        amount_ntd=1000,
        alert_threshold_percent=80,
        enabled=True,
    )
    bill = Bill(
        bank_code="CTBC",
        billing_month=period,
        total_amount=500,
        due_date=today,
    )
    db_session.add_all([budget, bill])
    await db_session.flush()
    db_session.add(
        Transaction(
            bill_id=bill.id,
            trans_date=today,
            merchant="Market",
            amount=500,
            currency="TWD",
        )
    )
    await db_session.commit()

    default_body = _dump_projection(await budget_status(db_session))
    current_body = _dump_projection(
        await budget_status(db_session, include_current_period=True)
    )

    assert default_body["data"][0]["current_period"] is None
    assert default_body["data"][0]["amount"] == {
        "currency": "TWD",
        "value": "1000",
    }
    current = current_body["data"][0]["current_period"]
    assert current == {
        "period_year_month": period,
        "amount": {"currency": "TWD", "value": "1000"},
        "current_amount": {"currency": "TWD", "value": "500"},
        "percent": 50.0,
        "threshold_breached": False,
        "alert_threshold_percent": 80,
    }


def _make_pipeline_run(
    run_id: str,
    *,
    status: PipelineRunStatus,
    created_at: datetime,
    terminal_reason: str | None,
) -> PipelineRun:
    raw_stage_error = (
        "PDF password=pdf-pass-123; OAuth refresh token=refresh-token-456; "
        "card=4111111111111111"
    )
    return PipelineRun(
        id=run_id,
        job_id=f"job-{run_id}",
        status=status,
        triggered_by="worker",
        params={"force": False, "bank_code": "CTBC"},
        current_stage="parse",
        current_stage_processed=2,
        current_stage_total=3,
        stage_summary=[
            {
                "stage": "parse",
                "ok": 2,
                "fail": 1,
                "elapsed_ms": 12,
                "counts": {"parsed": 2, "failed": 1},
                "errors": [raw_stage_error],
            }
        ],
        error_message="retries exhausted" if terminal_reason else None,
        started_at=created_at,
        completed_at=created_at,
        created_at=created_at,
        updated_at=created_at,
        terminal_reason=terminal_reason,
    )


async def test_pipeline_status_returns_latest_tie_break_and_needs_human(
    db_session: AsyncSession,
):
    created_at = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
    db_session.add_all(
        [
            _make_pipeline_run(
                "run-a",
                status=PipelineRunStatus.SUCCEEDED,
                created_at=created_at,
                terminal_reason="succeeded",
            ),
            _make_pipeline_run(
                "run-z",
                status=PipelineRunStatus.FAILED,
                created_at=created_at,
                terminal_reason="retries_exhausted",
            ),
        ]
    )
    await db_session.commit()

    body = _dump_projection(await pipeline_status(db_session))

    assert body["data"]["id"] == "run-z"
    assert body["data"]["status"] == "failed"
    assert body["data"]["needs_human"] is True
    errors = body["data"]["stage_summary"][0]["errors"]
    serialized_errors = "\n".join(errors)
    assert errors
    assert all(error.strip() for error in errors)
    assert "pdf-pass-123" not in serialized_errors
    assert "refresh-token-456" not in serialized_errors
    assert "4111111111111111" not in serialized_errors
    assert any(
        any(
            keyword in error.casefold()
            for keyword in ("fail", "review", "manual", "check")
        )
        or any(keyword in error for keyword in ("失敗", "人工", "檢查", "確認"))
        for error in errors
    )


async def test_pipeline_status_without_runs_raises_resource_not_found(
    db_session: AsyncSession,
):
    with pytest.raises(AgentQueryError) as caught:
        await pipeline_status(db_session)

    _assert_not_found(caught.value)
