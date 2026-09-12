"""Security and canonical DTO contracts for Agent service projections."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from ccas.services import bills, budgets, pipeline, transactions
from ccas.services.schemas import (
    AgentBill,
    AgentQueryError,
    AgentTransaction,
    BudgetCurrentPeriod,
    BudgetStatus,
    Money,
    PageMeta,
    PipelineStageSummary,
    PipelineStatus,
)
from ccas.storage.models import BudgetScope, PipelineRunStatus

NOW = datetime(2026, 3, 20, 12, 0, tzinfo=UTC)


def _assert_nullable(schema: dict[str, Any], field: str) -> None:
    variants = schema["properties"][field].get("anyOf", [])
    assert any(variant.get("type") == "null" for variant in variants)


def _assert_safe_error(error: AgentQueryError, *secrets: str) -> None:
    assert error.code == "needs_human"
    assert error.needs_human is True
    assert all(secret not in error.message for secret in secrets)


@pytest.mark.parametrize(
    ("model", "required", "nullable"),
    [
        (Money, {"currency", "value"}, set()),
        (
            PageMeta,
            {"page", "page_size", "total", "total_pages", "has_next"},
            set(),
        ),
        (
            AgentBill,
            {
                "id",
                "bank_code",
                "bank_name",
                "billing_month",
                "total_amount",
                "due_date",
                "is_paid",
                "created_at",
                "card_last4s",
                "reconciliation_key",
            },
            {"bank_name"},
        ),
        (
            AgentTransaction,
            {
                "id",
                "bill_id",
                "trans_date",
                "posting_date",
                "merchant",
                "amount",
                "original_amount",
                "card_last4",
                "category",
                "bank_code",
                "billing_month",
                "installment_current",
                "installment_total",
                "reconciliation_key",
            },
            {
                "posting_date",
                "original_amount",
                "card_last4",
                "category",
                "installment_current",
                "installment_total",
            },
        ),
        (
            BudgetCurrentPeriod,
            {
                "period_year_month",
                "amount",
                "current_amount",
                "percent",
                "threshold_breached",
                "alert_threshold_percent",
            },
            set(),
        ),
        (
            BudgetStatus,
            {
                "id",
                "scope",
                "scope_ref",
                "amount",
                "alert_threshold_percent",
                "enabled",
                "current_period",
            },
            {"scope_ref", "current_period"},
        ),
        (
            PipelineStageSummary,
            {"stage", "ok", "fail", "elapsed_ms", "counts", "errors"},
            set(),
        ),
        (
            PipelineStatus,
            {
                "id",
                "job_id",
                "status",
                "triggered_by",
                "params",
                "current_stage",
                "current_stage_processed",
                "current_stage_total",
                "stage_summary",
                "error_message",
                "started_at",
                "completed_at",
                "created_at",
                "updated_at",
                "needs_human",
            },
            {"current_stage", "error_message", "started_at", "completed_at"},
        ),
    ],
)
async def test_agent_payload_schema_has_canonical_required_and_nullable_fields(
    model: type[Any], required: set[str], nullable: set[str]
) -> None:
    schema = model.model_json_schema()

    assert set(schema["required"]) == required
    for field in nullable:
        _assert_nullable(schema, field)


def _valid_bill_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": 1,
        "bank_code": "CTBC",
        "bank_name": None,
        "billing_month": "2026-03",
        "total_amount": {"currency": "TWD", "value": "1234"},
        "due_date": date(2026, 4, 15),
        "is_paid": False,
        "created_at": NOW,
        "card_last4s": ["1234"],
        "reconciliation_key": "CTBC:2026-03:1234",
    }
    payload.update(overrides)
    return payload


def _valid_transaction_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": 7,
        "bill_id": 1,
        "trans_date": date(2026, 3, 14),
        "posting_date": None,
        "merchant": "Cafe",
        "amount": {"currency": "TWD", "value": "-250"},
        "original_amount": None,
        "card_last4": "1234",
        "category": None,
        "bank_code": "CTBC",
        "billing_month": "2026-03",
        "installment_current": None,
        "installment_total": None,
        "reconciliation_key": "1:2026-03-14:-250:Cafe",
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (AgentBill, _valid_bill_payload(card_last4s=["１２３４"])),
        (AgentBill, _valid_bill_payload(card_last4s=["12345"])),
        (AgentTransaction, _valid_transaction_payload(card_last4="12A4")),
        (AgentTransaction, _valid_transaction_payload(card_last4="１２３４")),
    ],
)
async def test_agent_payload_rejects_non_ascii_or_non_four_digit_cards(
    model: type[Any], payload: dict[str, Any]
) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(payload)


async def test_bill_projection_does_not_expose_secrets_in_bank_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bill = SimpleNamespace(
        id=1,
        bank_code="CTBC",
        billing_month="2026-03",
        total_amount=1234,
        due_date=date(2026, 4, 15),
        is_paid=False,
        file_path="/srv/ccas/private/statement.pdf",
        created_at=NOW,
    )
    bank_name = "中國信託 password=bank-secret 4111111111111111"
    bank_names = AsyncMock(return_value={"CTBC": bank_name})
    monkeypatch.setattr(bills, "fetch_bank_names", bank_names)
    monkeypatch.setattr(
        bills,
        "list_bills_query",
        AsyncMock(return_value=([bill], 1, 1, False)),
    )
    monkeypatch.setattr(
        bills,
        "fetch_card_last4s_for_bills",
        AsyncMock(return_value={1: ["1234"]}),
    )

    try:
        projection = await bills.list_bills(cast(Any, object()))
    except AgentQueryError as error:
        _assert_safe_error(error, "bank-secret", "4111111111111111")
    else:
        serialized = json.dumps(projection.payload.model_dump(mode="json"))
        assert bank_name not in serialized
        assert "bank-secret" not in serialized
        assert "4111111111111111" not in serialized
        assert "file_path" not in serialized

    bank_names.return_value = {"CTBC": "中國信託"}
    clean_projection = await bills.list_bills(cast(Any, object()))
    clean_payload = clean_projection.payload.model_dump(mode="json")
    assert clean_payload["data"][0]["bank_name"] == "中國信託"
    assert "file_path" not in json.dumps(clean_payload)


async def test_transaction_projection_redacts_category_and_keeps_negative_money(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = SimpleNamespace(
        id=7,
        bill_id=42,
        trans_date=date(2026, 3, 14),
        posting_date=None,
        merchant="Cafe",
        amount=-250,
        original_amount=-300,
        card_last4="1234",
        category="dining token=category-secret 4111111111111111",
        bill_bank_code="CTBC",
        bill_billing_month="2026-03",
        installment_current=None,
        installment_total=None,
        dup_ordinal=1,
        currency="TWD",
    )
    query_rows = AsyncMock(return_value=([row], 1, 1, False))
    monkeypatch.setattr(
        transactions,
        "query_transactions_query",
        query_rows,
    )

    try:
        projection = await transactions.query_transactions(cast(Any, object()))
    except AgentQueryError as error:
        _assert_safe_error(error, "category-secret", "4111111111111111")
    else:
        serialized = json.dumps(projection.payload.model_dump(mode="json"))
        assert "category-secret" not in serialized
        assert "4111111111111111" not in serialized

    row.category = "dining"
    clean_projection = await transactions.query_transactions(cast(Any, object()))
    payload = clean_projection.payload.model_dump(mode="json")
    assert payload["data"][0]["amount"] == {
        "currency": "TWD",
        "value": "-250",
    }
    assert payload["data"][0]["original_amount"] == {
        "currency": "TWD",
        "value": "-300",
    }


async def test_budget_projection_redacts_sensitive_scope_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    budget = SimpleNamespace(
        id=3,
        scope=BudgetScope.MONTHLY_CATEGORY,
        scope_ref="dining password=budget-secret 4111111111111111",
        amount_ntd=5000,
        alert_threshold_percent=80,
        enabled=True,
        created_at=NOW,
        updated_at=NOW,
    )
    budgets_query = AsyncMock(return_value=[budget])
    monkeypatch.setattr(
        budgets,
        "list_budgets_query",
        budgets_query,
    )

    try:
        projection = await budgets.budget_status(cast(Any, object()))
    except AgentQueryError as error:
        _assert_safe_error(error, "budget-secret", "4111111111111111")
    else:
        serialized = json.dumps(projection.payload.model_dump(mode="json"))
        assert "budget-secret" not in serialized
        assert "4111111111111111" not in serialized

    budget.scope_ref = "dining"
    clean_projection = await budgets.budget_status(cast(Any, object()))
    clean_payload = clean_projection.payload.model_dump(mode="json")
    assert clean_payload["data"][0]["scope_ref"] == "dining"
    assert clean_payload["data"][0]["current_period"] is None


async def test_budget_current_period_keeps_unrounded_threshold_semantics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    budget = SimpleNamespace(
        id=8,
        scope=BudgetScope.MONTHLY_TOTAL,
        scope_ref=None,
        amount_ntd=100_000,
        alert_threshold_percent=80,
        enabled=True,
        created_at=NOW,
        updated_at=NOW,
    )
    monkeypatch.setattr(
        budgets,
        "list_budgets_query",
        AsyncMock(return_value=[budget]),
    )
    monkeypatch.setattr(
        budgets,
        "aggregate_current_periods",
        AsyncMock(return_value={8: 79_999}),
    )

    projection = await budgets.budget_status(
        cast(Any, object()), include_current_period=True
    )
    current_period = projection.payload.model_dump(mode="json")["data"][0][
        "current_period"
    ]

    assert current_period["percent"] == 80.0
    assert current_period["threshold_breached"] is False


async def test_pipeline_projection_whitelists_and_sanitizes_all_agent_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_path = "/srv/ccas/private/worker.py"
    raw_connection = "postgresql://db.internal:5432/ccas"
    run = SimpleNamespace(
        id="run-1",
        job_id=f"job-{raw_path} token=job-secret",
        status=PipelineRunStatus.FAILED,
        triggered_by=f"scheduler {raw_path}",
        params={
            "force": True,
            "bank_code": "CTBC password=param-secret",
            "year": 2026,
            "month": "2026-03",
            "from_stage": f"parse {raw_path}",
            "to_stage": "notify",
            "token": "must-not-be-projected",
        },
        current_stage=f"parse {raw_path}",
        current_stage_processed=1,
        current_stage_total=2,
        stage_summary=[
            {
                "stage": f"parse {raw_path}",
                "ok": 1,
                "fail": 1,
                "elapsed_ms": 25,
                "counts": {f"internal {raw_path}": 2, "transactions": 1},
                "errors": [f"OperationalError: connection refused at {raw_connection}"],
            }
        ],
        error_message=(
            f"OperationalError: connection refused at {raw_path}; host {raw_connection}"
        ),
        terminal_reason=None,
        started_at=NOW,
        completed_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    monkeypatch.setattr(
        pipeline,
        "get_latest_pipeline_run",
        AsyncMock(return_value=run),
    )

    try:
        projection = await pipeline.pipeline_status(cast(Any, object()))
    except AgentQueryError as error:
        _assert_safe_error(error, "job-secret", "param-secret")
    else:
        serialized = json.dumps(projection.payload.model_dump(mode="json"))
        assert raw_path not in serialized
        assert raw_connection not in serialized
        assert "job-secret" not in serialized
        assert "param-secret" not in serialized

    run.job_id = "job-1"
    run.triggered_by = "scheduler"
    run.current_stage = "parse"
    run.params = {
        "force": True,
        "bank_code": "CTBC",
        "year": 2026,
        "month": "2026-03",
        "from_stage": "parse",
        "to_stage": "notify",
        "token": "must-not-be-projected",
    }
    run.stage_summary = [
        {
            "stage": "parse",
            "ok": 1,
            "fail": 1,
            "elapsed_ms": 25,
            "counts": {"transactions": 1},
            "errors": [f"OperationalError: connection refused at {raw_connection}"],
        }
    ]
    clean_projection = await pipeline.pipeline_status(cast(Any, object()))
    clean_payload = clean_projection.payload.model_dump(mode="json")
    clean_serialized = json.dumps(clean_payload)
    assert raw_connection not in clean_serialized
    assert raw_path not in clean_serialized
    assert "OperationalError" not in clean_serialized
    assert "manual review" in clean_serialized.lower()
    assert "token" not in clean_payload["data"]["params"]
    assert clean_payload["data"]["params"]["force"] is True
    assert clean_payload["data"]["stage_summary"][0]["counts"]["transactions"] == 1
