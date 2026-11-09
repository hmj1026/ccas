"""Agent 查詢錯誤種類與公開投影。

每個錯誤種類的對外文字在此釘住：外部 Agent 看到的字串變動必須是刻意的。
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from ccas.services.query_errors import (
    AgentQueryError,
    QueryErrorKind,
    public_query_error,
    public_unexpected_error,
)

K = QueryErrorKind

PINNED: dict[QueryErrorKind, tuple[str, str]] = {
    K.RESOURCE_NOT_FOUND: (
        "resource_not_found",
        "The requested resource was not found.",
    ),
    K.NO_PIPELINE_RUNS: (
        "resource_not_found",
        "No pipeline runs found.",
    ),
    K.INVALID_ARGUMENT: (
        "invalid_argument",
        "Invalid argument provided.",
    ),
    K.MALFORMED_BILLING_MONTH: (
        "needs_human",
        "Database contains malformed billing month; human review required.",
    ),
    K.MALFORMED_CARD_DATA: (
        "needs_human",
        "Database contains malformed card data; human review required.",
    ),
    K.MALFORMED_BILL_DATA: (
        "needs_human",
        "Database contains malformed bill data; human review required.",
    ),
    K.MALFORMED_BUDGET_DATA: (
        "needs_human",
        "Database contains malformed budget data; human review required.",
    ),
    K.MALFORMED_TRANSACTION_DATA: (
        "needs_human",
        "Database contains malformed transaction data; human review required.",
    ),
    K.MALFORMED_STAGE_SUMMARY: (
        "needs_human",
        "Database contains malformed stage summary data; human review required.",
    ),
    K.MALFORMED_PIPELINE_DATA: (
        "needs_human",
        "Database contains malformed pipeline data; human review required.",
    ),
    K.SENSITIVE_BILL_DATA: (
        "needs_human",
        "Bill data contains sensitive information requiring human review.",
    ),
    K.SENSITIVE_BUDGET_DATA: (
        "needs_human",
        "Budget data contains sensitive information requiring human review.",
    ),
    K.SENSITIVE_TRANSACTION: (
        "needs_human",
        "Transaction contains sensitive information requiring human review.",
    ),
    K.SENSITIVE_QUERY_RESULT: (
        "needs_human",
        "Query result contains sensitive information requiring human review.",
    ),
    K.SENSITIVE_PIPELINE_STAGE: (
        "needs_human",
        "Pipeline stage contains sensitive information requiring human review.",
    ),
    K.SENSITIVE_TRANSACTION_MERCHANT: (
        "needs_human",
        "Transaction merchant contains sensitive information.",
    ),
    K.SENSITIVE_PIPELINE_COUNT_KEY: (
        "needs_human",
        "Pipeline count key contains sensitive information.",
    ),
    K.SENSITIVE_PIPELINE_ID: (
        "needs_human",
        "Pipeline id contains sensitive information.",
    ),
    K.SENSITIVE_PIPELINE_JOB_ID: (
        "needs_human",
        "Pipeline job_id contains sensitive information.",
    ),
    K.SENSITIVE_PIPELINE_TRIGGERED_BY: (
        "needs_human",
        "Pipeline triggered_by contains sensitive information.",
    ),
    K.SENSITIVE_PIPELINE_CURRENT_STAGE: (
        "needs_human",
        "Pipeline current_stage contains sensitive information.",
    ),
    K.PIPELINE_COUNTS_INVALID: (
        "needs_human",
        "Pipeline counts must be nonnegative integers.",
    ),
    K.PIPELINE_NEEDS_HUMAN: (
        "needs_human",
        "Pipeline execution failed and requires human intervention.",
    ),
    K.PIPELINE_RETRIES_EXHAUSTED: (
        "needs_human",
        "Pipeline execution failed after retries were exhausted; "
        "manual review and check required.",
    ),
    K.INVALID_DATA: (
        "needs_human",
        "Database contains invalid data; human review required.",
    ),
    K.QUERY_FAILED: (
        "needs_human",
        "Agent query failed; manual review and check required.",
    ),
}

ID_KINDS = (K.BILL_NOT_FOUND, K.PIPELINE_RUN_NOT_FOUND)


def test_every_kind_is_pinned():
    assert set(PINNED) | set(ID_KINDS) == set(QueryErrorKind)


@pytest.mark.parametrize("kind", list(PINNED))
def test_kind_renders_pinned_code_text_and_needs_human(kind: QueryErrorKind):
    code, message = PINNED[kind]
    error = AgentQueryError(kind)

    assert (error.kind, error.code, error.message) == (kind, code, message)
    assert error.needs_human is (code == "needs_human")
    expected: dict[str, object] = {"code": code, "message": message}
    if code == "needs_human":
        expected["needs_human"] = True
    assert public_query_error(error) == expected


@pytest.mark.parametrize(
    ("kind", "ident", "expected"),
    [
        (K.BILL_NOT_FOUND, 123, "Bill #123 not found."),
        (K.BILL_NOT_FOUND, "123", "Bill #123 not found."),
        (K.PIPELINE_RUN_NOT_FOUND, 42, "Pipeline run #42 not found."),
        (
            K.PIPELINE_RUN_NOT_FOUND,
            999_999_999_999,
            "Pipeline run #999999999999 not found.",
        ),
    ],
)
def test_id_kinds_render_safe_ids(
    kind: QueryErrorKind, ident: int | str, expected: str
):
    error = AgentQueryError(kind, id=ident)
    assert error.code == "resource_not_found"
    assert public_query_error(error)["message"] == expected


@pytest.mark.parametrize(
    "ident", ["missing", 4111111111111111, "4111111111111111", 10**12, -1, True, "12a"]
)
@pytest.mark.parametrize("kind", ID_KINDS)
def test_unsafe_ids_fall_back_without_echo(kind: QueryErrorKind, ident: int | str):
    message = public_query_error(AgentQueryError(kind, id=ident))["message"]
    assert message == "The requested resource was not found."
    assert str(ident) not in message


def test_id_kind_requires_id():
    with pytest.raises(TypeError):
        AgentQueryError(K.BILL_NOT_FOUND)


def test_plain_kind_rejects_id():
    with pytest.raises(TypeError):
        AgentQueryError(K.INVALID_ARGUMENT, id=1)


def test_only_kinds_are_accepted():
    with pytest.raises(TypeError):
        AgentQueryError("resource_not_found")  # type: ignore[arg-type]


class _Model(BaseModel):
    value: int


def test_unexpected_validation_error_projects_invalid_data():
    with pytest.raises(ValidationError) as caught:
        _Model(value="x")  # type: ignore[arg-type]

    assert public_unexpected_error(caught.value) == {
        "code": "needs_human",
        "message": "Database contains invalid data; human review required.",
        "needs_human": True,
    }


def test_unexpected_other_error_projects_query_failed_without_detail():
    payload = public_unexpected_error(
        RuntimeError("SELECT * FROM secrets WHERE pw='x'")
    )

    assert payload == {
        "code": "needs_human",
        "message": "Agent query failed; manual review and check required.",
        "needs_human": True,
    }
