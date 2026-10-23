"""Regression coverage for exact budget alert thresholds and pending alerts."""

from __future__ import annotations

from collections.abc import Generator
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.config import get_settings
from ccas.scheduler.budget_evaluator import evaluate_budgets
from ccas.storage.models import (
    Bill,
    Budget,
    BudgetAlert,
    BudgetScope,
    Transaction,
)

ASSESSMENT_DATE = date(2026, 6, 15)
ASSESSMENT_MONTH = "2026-06"


@pytest.fixture(autouse=True)
def _telegram_settings(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "987654321")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    yield
    get_settings.cache_clear()  # type: ignore[attr-defined]


async def _create_budget_and_bill(
    session: AsyncSession, *, amounts: list[int]
) -> tuple[Budget, Bill]:
    budget = Budget(
        scope=BudgetScope.MONTHLY_TOTAL,
        scope_ref=None,
        amount_ntd=101,
        alert_threshold_percent=80,
        enabled=True,
    )
    bill = Bill(
        bank_code="CTBC",
        billing_month=ASSESSMENT_MONTH,
        total_amount=sum(amounts),
        due_date=date(2026, 6, 30),
        is_paid=False,
    )
    session.add_all([budget, bill])
    await session.flush()

    for index, amount in enumerate(amounts):
        session.add(
            Transaction(
                bill_id=bill.id,
                trans_date=ASSESSMENT_DATE,
                merchant=f"Transaction {index + 1}",
                amount=amount,
                currency="TWD",
            )
        )

    await session.commit()
    return budget, bill


async def _add_transaction(
    session: AsyncSession, bill: Bill, *, amount: int, merchant: str
) -> None:
    session.add(
        Transaction(
            bill_id=bill.id,
            trans_date=ASSESSMENT_DATE,
            merchant=merchant,
            amount=amount,
            currency="TWD",
        )
    )
    await session.commit()


async def _alerts(session: AsyncSession) -> list[BudgetAlert]:
    result = await session.execute(select(BudgetAlert).order_by(BudgetAlert.id))
    return list(result.scalars().all())


async def test_80_percent_alert_waits_for_exact_integer_threshold(
    db_session: AsyncSession,
) -> None:
    budget, bill = await _create_budget_and_bill(db_session, amounts=[80])

    with patch(
        "ccas.scheduler.budget_evaluator.send_message",
        new=AsyncMock(return_value=None),
    ) as send_message:
        at_80 = await evaluate_budgets(db_session, today=ASSESSMENT_DATE)

        assert at_80["alerts_triggered"] == 0
        assert await _alerts(db_session) == []
        send_message.assert_not_awaited()

        await _add_transaction(
            db_session, bill, amount=1, merchant="Threshold crossing"
        )
        at_81 = await evaluate_budgets(db_session, today=ASSESSMENT_DATE)

    alerts = await _alerts(db_session)
    assert at_81["alerts_triggered"] == 1
    assert len(alerts) == 1
    assert alerts[0].budget_id == budget.id
    assert alerts[0].threshold_breached_percent == 80
    assert alerts[0].current_amount_ntd == 81
    send_message.assert_awaited_once()


async def test_pending_alert_is_reused_only_after_exact_threshold_is_met(
    db_session: AsyncSession,
) -> None:
    budget, bill = await _create_budget_and_bill(db_session, amounts=[80])
    pending = BudgetAlert(
        budget_id=budget.id,
        period_year_month=ASSESSMENT_MONTH,
        threshold_breached_percent=80,
        current_amount_ntd=80,
        notified=False,
    )
    db_session.add(pending)
    await db_session.commit()
    pending_id = pending.id

    with patch(
        "ccas.scheduler.budget_evaluator.send_message",
        new=AsyncMock(return_value=None),
    ) as send_message:
        below_threshold = await evaluate_budgets(db_session, today=ASSESSMENT_DATE)

        assert below_threshold["alerts_triggered"] == 0
        alerts_before_crossing = await _alerts(db_session)
        assert len(alerts_before_crossing) == 1
        assert alerts_before_crossing[0].id == pending_id
        assert alerts_before_crossing[0].current_amount_ntd == 80
        send_message.assert_not_awaited()

        await _add_transaction(
            db_session, bill, amount=1, merchant="Threshold crossing"
        )
        at_threshold = await evaluate_budgets(db_session, today=ASSESSMENT_DATE)

    alerts_after_crossing = await _alerts(db_session)
    assert at_threshold["alerts_triggered"] == 1
    assert len(alerts_after_crossing) == 1
    assert alerts_after_crossing[0].id == pending_id
    assert alerts_after_crossing[0].current_amount_ntd == 81
    assert alerts_after_crossing[0].notified is True
    send_message.assert_awaited_once()


async def test_refund_delays_pending_alert_until_spending_recovers(
    db_session: AsyncSession,
) -> None:
    budget, bill = await _create_budget_and_bill(db_session, amounts=[81, -2])
    pending = BudgetAlert(
        budget_id=budget.id,
        period_year_month=ASSESSMENT_MONTH,
        threshold_breached_percent=80,
        current_amount_ntd=81,
        notified=False,
    )
    db_session.add(pending)
    await db_session.commit()
    pending_id = pending.id

    with patch(
        "ccas.scheduler.budget_evaluator.send_message",
        new=AsyncMock(return_value=None),
    ) as send_message:
        below_threshold_after_refund = await evaluate_budgets(
            db_session, today=ASSESSMENT_DATE
        )

        assert below_threshold_after_refund["alerts_triggered"] == 0
        send_message.assert_not_awaited()

        await _add_transaction(db_session, bill, amount=2, merchant="Spending recovery")
        after_recovery = await evaluate_budgets(db_session, today=ASSESSMENT_DATE)

    alerts = await _alerts(db_session)
    assert after_recovery["alerts_triggered"] == 1
    assert len(alerts) == 1
    assert alerts[0].id == pending_id
    assert alerts[0].current_amount_ntd == 81
    assert alerts[0].notified is True
    send_message.assert_awaited_once()
