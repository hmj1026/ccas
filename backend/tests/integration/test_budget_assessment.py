"""Budget assessment through its public interface and real SQLite aggregation."""

from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.budget_assessment import assess_budgets
from ccas.storage.models import BankConfig, Bill, Budget, BudgetScope, Transaction


@pytest.mark.parametrize(
    ("limit", "spent", "threshold", "percent", "breached", "full"),
    [
        (101, 80, 80, 79.21, False, False),
        (101, 81, 80, 80.2, True, False),
        (100_000, 79_999, 80, 80.0, False, False),
        (100, -20, 80, -20.0, False, False),
        (0, 80, 80, 0.0, False, False),
        (-100, 80, 80, 0.0, False, False),
        (100, 100, 100, 100.0, True, True),
        (9_007_199_254_740_993, 9_007_199_254_740_992, 100, 100.0, False, False),
    ],
)
async def test_assessment_uses_exact_thresholds(
    db_session: AsyncSession,
    limit: int,
    spent: int,
    threshold: int,
    percent: float,
    breached: bool,
    full: bool,
) -> None:
    db_session.add(BankConfig(bank_code="CTBC", bank_name="CTBC", gmail_filter="x"))
    bill = Bill(
        bank_code="CTBC",
        billing_month="2026-03",
        total_amount=spent,
        due_date=date(2026, 4, 1),
    )
    budget = Budget(
        scope=BudgetScope.MONTHLY_TOTAL,
        amount_ntd=limit,
        alert_threshold_percent=threshold,
        enabled=False,
    )
    db_session.add_all([bill, budget])
    await db_session.flush()
    db_session.add(
        Transaction(
            bill_id=bill.id,
            trans_date=date(2026, 2, 20),
            merchant="Purchase or refund",
            amount=spent,
            currency="TWD",
        )
    )
    await db_session.commit()

    result = (await assess_budgets(db_session, [budget], "2026-03"))[budget.id]

    assert result.period_year_month == "2026-03"
    assert result.spent_amount_ntd == spent
    assert result.percent == percent
    assert result.threshold_breached is breached
    assert result.reaches(100) is full


async def test_batch_assessment_uses_billing_month_and_current_settings(
    db_session: AsyncSession,
) -> None:
    db_session.add(BankConfig(bank_code="CTBC", bank_name="CTBC", gmail_filter="x"))
    bill = Bill(
        bank_code="CTBC",
        billing_month="2026-03",
        total_amount=80,
        due_date=date(2026, 4, 1),
    )
    budgets = [
        Budget(
            scope=scope,
            scope_ref=ref,
            amount_ntd=101,
            alert_threshold_percent=80,
            enabled=True,
        )
        for scope, ref in [
            (BudgetScope.MONTHLY_TOTAL, None),
            (BudgetScope.MONTHLY_BANK, "CTBC"),
            (BudgetScope.MONTHLY_CATEGORY, "food"),
        ]
    ]
    db_session.add_all([bill, *budgets])
    await db_session.flush()
    for amount in [100, -20]:
        db_session.add(
            Transaction(
                bill_id=bill.id,
                trans_date=date(2026, 2, 20),
                merchant="Purchase or refund",
                amount=amount,
                currency="TWD",
                category="food",
            )
        )
    await db_session.commit()

    march = await assess_budgets(db_session, budgets, "2026-03")
    assert [r.spent_amount_ntd for r in march.values()] == [80, 80, 80]
    assert not any(r.threshold_breached for r in march.values())
    february = await assess_budgets(db_session, budgets, "2026-02")
    assert [r.spent_amount_ntd for r in february.values()] == [0, 0, 0]
    for budget in budgets:
        budget.amount_ntd = 100
    await db_session.commit()
    changed = await assess_budgets(db_session, budgets, "2026-03")
    assert all(r.threshold_breached for r in changed.values())
    assert await assess_budgets(db_session, [], "2026-03") == {}
