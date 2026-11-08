"""Agent 查詢錯誤：封閉的錯誤種類與公開投影。

REST、MCP 與 CLI 回報 Agent 查詢錯誤時都經過本模組：

- :class:`QueryErrorKind` 是封閉的錯誤種類。每個種類固定 machine-readable
  ``code``、是否 ``needs_human``，以及英文訊息範本。
- :class:`AgentQueryError` 只能以錯誤種類建立；拋出端無法自行撰寫訊息文字。
- :func:`public_query_error` / :func:`public_unexpected_error` 產生三個 adapter
  共用的公開 envelope ``{code, message, needs_human?}``。

範本唯一允許的參數是呼叫端提供的識別 ``id``，且只在它是 1–12 位數字時才
顯示；其他值（任意字串、類似卡號的長數字）改用不含識別的範本，確保呼叫端
輸入與資料庫內容永不回顯（ADR-0001 第 5 點）。12 位數上限刻意低於
``services.identity.PAN_REGEX`` 的 13 位數卡號下限。
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any

from pydantic import ValidationError

from ccas.errors import CcasError

_SAFE_ID = re.compile(r"[0-9]{1,12}")
_FALLBACK_NOT_FOUND = "The requested resource was not found."


class QueryErrorKind(Enum):
    """封閉的 Agent 查詢錯誤種類：``(code, template)``。

    含 ``{id}`` 的範本需要 ``id`` 參數；其餘範本不接受任何參數。
    """

    # resource_not_found
    RESOURCE_NOT_FOUND = ("resource_not_found", _FALLBACK_NOT_FOUND)
    BILL_NOT_FOUND = ("resource_not_found", "Bill #{id} not found.")
    PIPELINE_RUN_NOT_FOUND = ("resource_not_found", "Pipeline run #{id} not found.")
    NO_PIPELINE_RUNS = ("resource_not_found", "No pipeline runs found.")
    # invalid_argument
    INVALID_ARGUMENT = ("invalid_argument", "Invalid argument provided.")
    # needs_human: malformed stored data
    MALFORMED_BILLING_MONTH = (
        "needs_human",
        "Database contains malformed billing month; human review required.",
    )
    MALFORMED_CARD_DATA = (
        "needs_human",
        "Database contains malformed card data; human review required.",
    )
    MALFORMED_BILL_DATA = (
        "needs_human",
        "Database contains malformed bill data; human review required.",
    )
    MALFORMED_BUDGET_DATA = (
        "needs_human",
        "Database contains malformed budget data; human review required.",
    )
    MALFORMED_TRANSACTION_DATA = (
        "needs_human",
        "Database contains malformed transaction data; human review required.",
    )
    MALFORMED_STAGE_SUMMARY = (
        "needs_human",
        "Database contains malformed stage summary data; human review required.",
    )
    MALFORMED_PIPELINE_DATA = (
        "needs_human",
        "Database contains malformed pipeline data; human review required.",
    )
    INVALID_DATA = (
        "needs_human",
        "Database contains invalid data; human review required.",
    )
    # needs_human: sensitive content blocked from the response
    SENSITIVE_BILL_DATA = (
        "needs_human",
        "Bill data contains sensitive information requiring human review.",
    )
    SENSITIVE_BUDGET_DATA = (
        "needs_human",
        "Budget data contains sensitive information requiring human review.",
    )
    SENSITIVE_TRANSACTION = (
        "needs_human",
        "Transaction contains sensitive information requiring human review.",
    )
    SENSITIVE_QUERY_RESULT = (
        "needs_human",
        "Query result contains sensitive information requiring human review.",
    )
    SENSITIVE_PIPELINE_STAGE = (
        "needs_human",
        "Pipeline stage contains sensitive information requiring human review.",
    )
    SENSITIVE_TRANSACTION_MERCHANT = (
        "needs_human",
        "Transaction merchant contains sensitive information.",
    )
    SENSITIVE_PIPELINE_COUNT_KEY = (
        "needs_human",
        "Pipeline count key contains sensitive information.",
    )
    SENSITIVE_PIPELINE_ID = (
        "needs_human",
        "Pipeline id contains sensitive information.",
    )
    SENSITIVE_PIPELINE_JOB_ID = (
        "needs_human",
        "Pipeline job_id contains sensitive information.",
    )
    SENSITIVE_PIPELINE_TRIGGERED_BY = (
        "needs_human",
        "Pipeline triggered_by contains sensitive information.",
    )
    SENSITIVE_PIPELINE_CURRENT_STAGE = (
        "needs_human",
        "Pipeline current_stage contains sensitive information.",
    )
    # needs_human: pipeline state
    PIPELINE_COUNTS_INVALID = (
        "needs_human",
        "Pipeline counts must be nonnegative integers.",
    )
    PIPELINE_NEEDS_HUMAN = (
        "needs_human",
        "Pipeline execution failed and requires human intervention.",
    )
    PIPELINE_RETRIES_EXHAUSTED = (
        "needs_human",
        "Pipeline execution failed after retries were exhausted; "
        "manual review and check required.",
    )
    # needs_human: unexpected failure (exception detail is never exposed)
    QUERY_FAILED = (
        "needs_human",
        "Agent query failed; manual review and check required.",
    )

    @property
    def code(self) -> str:
        return self.value[0]

    @property
    def template(self) -> str:
        return self.value[1]

    @property
    def takes_id(self) -> bool:
        return "{id}" in self.template


class AgentQueryError(CcasError):
    """Agent 查詢的業務錯誤；只能以 :class:`QueryErrorKind` 建立。

    Args:
        kind: 錯誤種類，決定 ``code``、``needs_human`` 與訊息範本。
        id: 範本含 ``{id}`` 時必填（呼叫端提供的識別）；其他種類不得提供。

    Raises:
        TypeError: ``kind`` 不是錯誤種類，或 ``id`` 與範本不符。
    """

    def __init__(self, kind: QueryErrorKind, *, id: int | str | None = None) -> None:  # noqa: A002
        if not isinstance(kind, QueryErrorKind):
            raise TypeError(f"AgentQueryError requires a QueryErrorKind, got {kind!r}")
        if kind.takes_id != (id is not None):
            verb = "requires" if kind.takes_id else "does not accept"
            raise TypeError(f"{kind.name} {verb} an id")

        message = kind.template
        if kind.takes_id:
            text = str(id) if isinstance(id, str) or type(id) is int else ""
            message = (
                kind.template.format(id=text)
                if _SAFE_ID.fullmatch(text)
                else _FALLBACK_NOT_FOUND
            )
        super().__init__(message)
        self.kind = kind
        self.code = kind.code
        self.needs_human = kind.code == "needs_human"
        self.message = message


def public_query_error(error: AgentQueryError) -> dict[str, Any]:
    """REST、MCP 與 CLI 共用的公開業務錯誤 envelope。"""
    payload: dict[str, Any] = {"code": error.code, "message": error.message}
    if error.needs_human:
        payload["needs_human"] = True
    return payload


def unexpected_error_kind(exc: BaseException) -> QueryErrorKind:
    """非 :class:`AgentQueryError` 例外對應的錯誤種類。"""
    if isinstance(exc, ValidationError):
        return QueryErrorKind.INVALID_DATA
    return QueryErrorKind.QUERY_FAILED


def public_unexpected_error(exc: BaseException) -> dict[str, Any]:
    """非 :class:`AgentQueryError` 例外的公開 envelope；永不包含例外內容。"""
    return public_query_error(AgentQueryError(unexpected_error_kind(exc)))
