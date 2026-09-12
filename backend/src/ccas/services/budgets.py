"""Budgets Agent query services."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.services.identity import contains_sensitive_data
from ccas.services.schemas import (
    AgentQueryError,
    BudgetCurrentPeriod,
    BudgetStatus,
    BudgetStatusInput,
    BudgetStatusResult,
    Money,
    ServiceProjection,
)
from ccas.storage.agent_queries import list_budgets_query
from ccas.storage.models import BudgetScope
from ccas.storage.queries import aggregate_current_periods


async def budget_status(
    session: AsyncSession,
    *,
    scope: (
        Literal["monthly_total", "monthly_category", "monthly_bank"] | str | None
    ) = None,
    include_current_period: bool = False,
) -> ServiceProjection[BudgetStatusResult]:
    """Fetch budget statuses with optional current period spending aggregation."""
    try:
        input_dto = BudgetStatusInput(
            scope=scope,  # type: ignore[arg-type]
            include_current_period=include_current_period,
        )
    except ValidationError as exc:
        raise AgentQueryError("invalid_argument", "Invalid argument provided.") from exc

    scope_filter = input_dto.scope
    budgets = await list_budgets_query(session, scope=scope_filter)

    today = date.today()
    period = f"{today.year:04d}-{today.month:02d}"

    current_map: dict[int, int] = {}
    if input_dto.include_current_period:
        current_map = await aggregate_current_periods(session, budgets, period)

    items: list[BudgetStatus] = []
    rest_metadata: dict[str, Any] = {}

    for b in budgets:
        if b.scope_ref and contains_sensitive_data(b.scope_ref):
            raise AgentQueryError(
                "needs_human",
                "Budget data contains sensitive information requiring human review.",
                needs_human=True,
            )

        current_dto: BudgetCurrentPeriod | None = None
        if input_dto.include_current_period:
            current_val = current_map.get(b.id, 0)
            raw_percent = (
                (current_val / b.amount_ntd * 100.0) if b.amount_ntd > 0 else 0.0
            )
            threshold_breached = raw_percent >= b.alert_threshold_percent
            percent = round(raw_percent, 2)
            current_dto = BudgetCurrentPeriod(
                period_year_month=period,
                amount=Money(currency="TWD", value=str(int(b.amount_ntd))),
                current_amount=Money(currency="TWD", value=str(int(current_val))),
                percent=percent,
                threshold_breached=threshold_breached,
                alert_threshold_percent=b.alert_threshold_percent,
            )

        scope_val = b.scope.value if isinstance(b.scope, BudgetScope) else str(b.scope)

        try:
            status_item = BudgetStatus(
                id=b.id,
                scope=scope_val,  # type: ignore[arg-type]
                scope_ref=b.scope_ref,
                amount=Money(currency="TWD", value=str(int(b.amount_ntd))),
                alert_threshold_percent=b.alert_threshold_percent,
                enabled=b.enabled,
                current_period=current_dto,
            )
        except ValidationError as exc:
            raise AgentQueryError(
                "needs_human",
                "Database contains malformed budget data; human review required.",
                needs_human=True,
            ) from exc

        items.append(status_item)
        current_ntd = (
            current_map.get(b.id) if input_dto.include_current_period else None
        )
        rest_metadata[str(b.id)] = {
            "created_at": b.created_at,
            "updated_at": b.updated_at,
            "current_amount_ntd": current_ntd,
        }

    return ServiceProjection(
        payload=BudgetStatusResult(data=items),
        rest_metadata=rest_metadata,
    )
