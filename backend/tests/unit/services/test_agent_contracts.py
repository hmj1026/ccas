"""Pure contract tests for the Agent service DTOs and query inputs."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from ccas.config import Settings
from ccas.services.schemas import (
    AgentQueryError,
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


@pytest.mark.parametrize(
    ("code", "needs_human"),
    [
        ("resource_not_found", False),
        ("invalid_argument", False),
        ("needs_human", True),
    ],
)
def test_agent_query_error_exposes_allowed_code_and_optional_data(
    code: str, needs_human: bool
) -> None:
    error = AgentQueryError(
        code=code,
        message="Use a valid query or inspect the source record.",
        needs_human=needs_human,
        data={"resource": "bill"},
    )

    assert error.code == code
    assert error.message
    assert error.needs_human is needs_human
    assert error.data == {"resource": "bill"}


@pytest.mark.parametrize("code", ["unknown", ""])
def test_agent_query_error_rejects_unknown_codes(code: str) -> None:
    with pytest.raises(ValueError):
        AgentQueryError(code=code, message="not actionable")


@pytest.mark.parametrize("code", ["resource_not_found", "invalid_argument"])
def test_agent_query_error_cannot_mark_nonhuman_codes_for_human_review(
    code: str,
) -> None:
    with pytest.raises(ValueError):
        AgentQueryError(
            code=code,
            message="not actionable",
            needs_human=True,
        )


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
