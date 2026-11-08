"""Pure contract tests for the Agent service DTOs and query inputs."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from ccas.config import Settings
from ccas.services.query_errors import (
    AgentQueryError,
    QueryErrorKind,
    public_query_error,
)
from ccas.services.schemas import (
    BudgetStatusInput,
    EmptyInput,
    GetBillInput,
    ListBillsInput,
    Money,
    QueryTransactionsInput,
)

AGENT_INPUT_MODELS = (
    ListBillsInput,
    GetBillInput,
    QueryTransactionsInput,
    EmptyInput,
    BudgetStatusInput,
)


def test_public_error_preserves_safe_bill_identity_message() -> None:
    payload = public_query_error(AgentQueryError(QueryErrorKind.BILL_NOT_FOUND, id=42))
    assert payload == {"code": "resource_not_found", "message": "Bill #42 not found."}


@pytest.mark.parametrize(
    "identity", ["4111111111111111", "999999999999999999999999999999"]
)
def test_public_error_sanitizes_sensitive_numeric_bill_template(identity: str) -> None:
    payload = public_query_error(
        AgentQueryError(QueryErrorKind.BILL_NOT_FOUND, id=identity)
    )
    assert set(payload) == {"code", "message"}
    assert payload["code"] == "resource_not_found"
    assert identity not in payload["message"]
    assert payload["message"].strip()


def test_agent_input_defaults_match_tool_contracts() -> None:
    bills = ListBillsInput()
    transactions = QueryTransactionsInput()
    budget = BudgetStatusInput()

    assert bills.status == "all"
    assert bills.page == 1
    assert bills.page_size == 20
    assert transactions.sort == "trans_date_desc"
    assert transactions.page == 1
    assert transactions.page_size == 20
    assert budget.scope is None
    assert budget.include_current_period is False
    assert EmptyInput().model_dump() == {}


def test_agent_input_json_schemas_forbid_extra_properties() -> None:
    for model in AGENT_INPUT_MODELS:
        assert model.model_json_schema()["additionalProperties"] is False


@pytest.mark.parametrize(
    ("model", "kwargs"),
    [
        (ListBillsInput, {"unexpected": "value"}),
        (GetBillInput, {"bill_id": 1, "unexpected": "value"}),
        (QueryTransactionsInput, {"unexpected": "value"}),
        (EmptyInput, {"unexpected": "value"}),
        (BudgetStatusInput, {"unexpected": "value"}),
    ],
)
def test_agent_inputs_reject_extra_properties(
    model: Any, kwargs: dict[str, Any]
) -> None:
    with pytest.raises(ValidationError):
        model(**kwargs)


@pytest.mark.parametrize(
    ("model", "kwargs"),
    [
        (GetBillInput, {"bill_id": 0}),
        (ListBillsInput, {"year": 1999}),
        (ListBillsInput, {"year": 2100}),
        (ListBillsInput, {"page": 0}),
        (ListBillsInput, {"page_size": 0}),
        (ListBillsInput, {"page_size": 101}),
        (ListBillsInput, {"month": "2026-13"}),
        (ListBillsInput, {"month": "2026-1"}),
        (QueryTransactionsInput, {"month": "March"}),
        (QueryTransactionsInput, {"q": "x"}),
        (QueryTransactionsInput, {"sort": "date_desc"}),
        (BudgetStatusInput, {"scope": "weekly"}),
    ],
)
def test_agent_inputs_reject_invalid_bounds_and_formats(
    model: Any, kwargs: dict[str, Any]
) -> None:
    with pytest.raises(ValidationError):
        model(**kwargs)


@pytest.mark.parametrize(
    ("model", "kwargs"),
    [
        (ListBillsInput, {"year": True}),
        (ListBillsInput, {"page": "1"}),
        (GetBillInput, {"bill_id": "1"}),
        (QueryTransactionsInput, {"page_size": False}),
        (BudgetStatusInput, {"include_current_period": 1}),
    ],
)
def test_agent_inputs_use_strict_integer_and_boolean_types(
    model: Any, kwargs: dict[str, Any]
) -> None:
    with pytest.raises(ValidationError):
        model(**kwargs)


@pytest.mark.parametrize("value", ["-1234", "0", "12.50"])
def test_money_preserves_twd_decimal_strings(value: str) -> None:
    money = Money(currency="TWD", value=value)

    assert money.currency == "TWD"
    assert money.value == value
    assert money.model_dump(mode="json") == {"currency": "TWD", "value": value}


def test_budget_input_accepts_explicit_billing_month() -> None:
    assert BudgetStatusInput(month="2026-03").model_dump()["month"] == "2026-03"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"currency": "USD", "value": "10"},
        {"currency": "TWD", "value": "1e3"},
        {"currency": "TWD", "value": "NaN"},
        {"currency": "TWD", "value": 1.5},
    ],
)
def test_money_rejects_non_twd_scientific_and_float_values(
    kwargs: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError):
        Money(**kwargs)


def test_settings_agent_write_enabled_defaults_to_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("API_TOKEN", "test-token")
    monkeypatch.delenv("AGENT_WRITE_ENABLED", raising=False)

    settings = Settings(_env_file=None)

    assert settings.agent_write_enabled is False


def test_settings_agent_write_enabled_reads_true_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("API_TOKEN", "test-token")
    monkeypatch.setenv("AGENT_WRITE_ENABLED", "true")

    settings = Settings(_env_file=None)

    assert settings.agent_write_enabled is True
