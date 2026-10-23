"""Assess billing-month spending against current budget settings.

Query and alert adapters share this module; delivery and alert history remain
with the scheduler. Aggregation retains refunds and uses Bill.billing_month.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from ccas.storage.models import Budget
from ccas.storage.queries import aggregate_current_periods


@dataclass(frozen=True)
class BudgetAssessmentResult:
    """One budget's assessment, independent of transport and alert state."""

    budget_id: int
    period_year_month: str
    amount_ntd: int
    spent_amount_ntd: int
    alert_threshold_percent: int

    @property
    def percent(self) -> float:
        """Display rounding never participates in threshold decisions."""
        if self.amount_ntd <= 0:
            return 0.0
        return round(self.spent_amount_ntd / self.amount_ntd * 100.0, 2)

    def reaches(self, threshold_percent: int) -> bool:
        """Compare exact integer amounts, including fractional-NTD cutoffs."""
        return (
            self.amount_ntd > 0
            and self.spent_amount_ntd * 100 >= self.amount_ntd * threshold_percent
        )

    @property
    def threshold_breached(self) -> bool:
        return self.reaches(self.alert_threshold_percent)


async def assess_budgets(
    session: AsyncSession,
    budgets: Sequence[Budget],
    period_year_month: str,
) -> dict[int, BudgetAssessmentResult]:
    """Assess selected budgets for a validated ASCII YYYY-MM billing month.

    Callers select budgets (including disabled ones for reads) and the month;
    this module owns batched spending and exact threshold policy. Current
    settings apply even to historical months; no historical snapshot is used.
    """
    spending = await aggregate_current_periods(session, budgets, period_year_month)
    return {
        budget.id: BudgetAssessmentResult(
            budget_id=budget.id,
            period_year_month=period_year_month,
            amount_ntd=budget.amount_ntd,
            spent_amount_ntd=spending.get(budget.id, 0),
            alert_threshold_percent=budget.alert_threshold_percent,
        )
        for budget in budgets
    }
