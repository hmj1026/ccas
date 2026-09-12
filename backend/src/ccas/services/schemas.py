"""Agent services canonical Pydantic v2 schemas and envelopes.

All Agent-facing DTOs strictly adhere to the agent-mcp-interface and
reconciliation-identity specifications with extra="forbid".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ccas.errors import CcasError

ALLOWED_QUERY_ERROR_CODES: set[str] = {
    "resource_not_found",
    "invalid_argument",
    "needs_human",
}


class AgentQueryError(CcasError):
    """Business query error for Agent service queries.

    Uses standardized machine-readable codes (resource_not_found,
    invalid_argument, needs_human) with safe, sanitized human-readable
    messages that never leak credentials or internal paths.
    """

    DEFAULT_MESSAGES: dict[str, str] = {
        "resource_not_found": "The requested resource was not found.",
        "invalid_argument": "Invalid argument provided.",
        "needs_human": "Pipeline execution failed and requires human intervention.",
    }

    def __init__(
        self,
        code: str,
        message: str | None = None,
        *,
        needs_human: bool | None = None,
        data: Any = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        if code not in ALLOWED_QUERY_ERROR_CODES:
            raise ValueError(f"Unknown AgentQueryError code: {code!r}")
        if needs_human is True and code != "needs_human":
            raise ValueError(f"needs_human=True is not permitted for code {code!r}")

        resolved_message = (
            message
            if message is not None
            else self.DEFAULT_MESSAGES.get(code, "An error occurred.")
        )
        super().__init__(resolved_message, context=context)
        self.code = code
        self.message = resolved_message
        self.needs_human = (
            needs_human if needs_human is not None else (code == "needs_human")
        )
        self.data = data


def validate_payload_safety(obj: Any) -> None:
    """Recursively validate that public payload contains no sensitive data."""
    from ccas.services.identity import contains_sensitive_data

    if isinstance(obj, str):
        if contains_sensitive_data(obj):
            raise AgentQueryError(
                "needs_human",
                "Query result contains sensitive information requiring human review.",
                needs_human=True,
            )
    elif isinstance(obj, BaseModel):
        for field_name in type(obj).model_fields:
            validate_payload_safety(getattr(obj, field_name))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str) and contains_sensitive_data(k):
                raise AgentQueryError(
                    "needs_human",
                    (
                        "Query result contains sensitive information "
                        "requiring human review."
                    ),
                    needs_human=True,
                )
            validate_payload_safety(v)
    elif isinstance(obj, (list, tuple, set)):
        for item in obj:
            validate_payload_safety(item)


@dataclass
class ServiceProjection[T]:
    """Internal service projection seam.

    Carries the Agent Pydantic payload alongside internal `rest_metadata`
    which is used by REST compatibility adapters and excluded from public
    Agent DTO serialization.
    """

    payload: T
    rest_metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_payload_safety(self.payload)


# --- Canonical Output DTOs ---


class Money(BaseModel):
    """Money representation in non-scientific decimal integer-dollar TWD string."""

    model_config = ConfigDict(extra="forbid", strict=True)

    currency: Literal["TWD"]
    value: str = Field(pattern=r"^-?[0-9]+(?:\.[0-9]+)?$")


class PageMeta(BaseModel):
    """Canonical pagination metadata."""

    model_config = ConfigDict(extra="forbid")

    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)
    total_pages: int = Field(ge=1)
    has_next: bool


class AgentBill(BaseModel):
    """Canonical bill representation for Agent interfaces."""

    model_config = ConfigDict(extra="forbid")

    id: int
    bank_code: str
    bank_name: str | None
    billing_month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    total_amount: Money
    due_date: date
    is_paid: bool
    created_at: datetime
    card_last4s: list[Annotated[str, Field(pattern=r"^[0-9]{4}$")]]
    reconciliation_key: str


class AgentTransaction(BaseModel):
    """Canonical transaction representation for Agent interfaces."""

    model_config = ConfigDict(extra="forbid")

    id: int
    bill_id: int
    trans_date: date
    posting_date: date | None
    merchant: str
    amount: Money
    original_amount: Money | None
    card_last4: Annotated[str, Field(pattern=r"^[0-9]{4}$")] | None
    category: str | None
    bank_code: str
    billing_month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    installment_current: int | None
    installment_total: int | None
    reconciliation_key: str


class BudgetCurrentPeriod(BaseModel):
    """Canonical budget current period spending status."""

    model_config = ConfigDict(extra="forbid")

    period_year_month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    amount: Money
    current_amount: Money
    percent: float
    threshold_breached: bool
    alert_threshold_percent: int = Field(ge=1, le=100)


class BudgetStatus(BaseModel):
    """Canonical budget status."""

    model_config = ConfigDict(extra="forbid")

    id: int
    scope: Literal["monthly_total", "monthly_category", "monthly_bank"]
    scope_ref: str | None
    amount: Money
    alert_threshold_percent: int = Field(ge=1, le=100)
    enabled: bool
    current_period: BudgetCurrentPeriod | None


class PipelineStageSummary(BaseModel):
    """Canonical summary for a completed or failed pipeline stage."""

    model_config = ConfigDict(extra="forbid")

    stage: str
    ok: int = Field(ge=0)
    fail: int = Field(ge=0)
    elapsed_ms: int = Field(ge=0)
    counts: dict[str, Annotated[int, Field(ge=0)]]
    errors: list[str]


class PipelineStatus(BaseModel):
    """Canonical pipeline run status."""

    model_config = ConfigDict(extra="forbid")

    id: str
    job_id: str
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    triggered_by: str
    params: dict[str, Any]
    current_stage: str | None
    current_stage_processed: int = Field(ge=0)
    current_stage_total: int = Field(ge=0)
    stage_summary: list[PipelineStageSummary]
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    needs_human: bool


# --- Success Envelope Classes ---


class BillsPage(BaseModel):
    """Envelope for list_bills tool result."""

    model_config = ConfigDict(extra="forbid")

    data: list[AgentBill]
    pagination: PageMeta


class BillResult(BaseModel):
    """Envelope for get_bill tool result."""

    model_config = ConfigDict(extra="forbid")

    data: AgentBill


class TransactionsPage(BaseModel):
    """Envelope for query_transactions tool result."""

    model_config = ConfigDict(extra="forbid")

    data: list[AgentTransaction]
    pagination: PageMeta


class PaymentDueResult(BaseModel):
    """Envelope for get_payment_due tool result."""

    model_config = ConfigDict(extra="forbid")

    data: list[AgentBill]


class BudgetStatusResult(BaseModel):
    """Envelope for budget_status tool result."""

    model_config = ConfigDict(extra="forbid")

    data: list[BudgetStatus]


class PipelineStatusResult(BaseModel):
    """Envelope for pipeline_status tool result."""

    model_config = ConfigDict(extra="forbid")

    data: PipelineStatus


# --- Input Validation Models ---


class ListBillsInput(BaseModel):
    """Input parameters for list_bills."""

    model_config = ConfigDict(extra="forbid", strict=True)

    month: str | None = Field(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    year: int | None = Field(default=None, ge=2000, le=2099)
    bank_code: str | None = None
    status: Literal["all", "paid", "unpaid"] = "all"
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class GetBillInput(BaseModel):
    """Input parameters for get_bill."""

    model_config = ConfigDict(extra="forbid", strict=True)

    bill_id: int = Field(ge=1)


class QueryTransactionsInput(BaseModel):
    """Input parameters for query_transactions."""

    model_config = ConfigDict(extra="forbid", strict=True)

    month: str | None = Field(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    year: int | None = Field(default=None, ge=2000, le=2099)
    bank_code: str | None = None
    category: str | None = None
    q: str | None = Field(default=None, min_length=2)
    sort: Literal[
        "trans_date_asc",
        "trans_date_desc",
        "amount_asc",
        "amount_desc",
        "merchant_asc",
        "merchant_desc",
    ] = "trans_date_desc"
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class EmptyInput(BaseModel):
    """Input parameters for parameterless tools (get_payment_due, pipeline_status)."""

    model_config = ConfigDict(extra="forbid", strict=True)


class BudgetStatusInput(BaseModel):
    """Input parameters for budget_status."""

    model_config = ConfigDict(extra="forbid", strict=True)

    scope: Literal["monthly_total", "monthly_category", "monthly_bank"] | None = None
    include_current_period: bool = False
