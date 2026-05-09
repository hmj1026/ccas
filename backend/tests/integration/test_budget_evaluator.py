"""Integration tests for budget evaluator (§6.6-§6.10).

驗證：
- 80% threshold 觸發
- 100% threshold 也觸發（再觸發更高 threshold）
- 同月同 budget 同 threshold 不重複觸發
- enabled=false 不觸發
- Telegram 未設定時不 raise
- 多個觸發合併單則訊息（聚合）
"""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.scheduler.budget_evaluator import evaluate_budgets
from ccas.storage.models import (
    BankConfig,
    Bill,
    Budget,
    BudgetAlert,
    BudgetScope,
    Transaction,
)


@pytest.fixture(autouse=True)
def _set_telegram(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "test-chat")
    from ccas.config import get_settings

    get_settings.cache_clear()  # type: ignore[attr-defined]


async def _seed_bank_bill(
    session: AsyncSession,
    *,
    bank_code: str = "CTBC",
    period_ym: str | None = None,
    txns: list[tuple[int, str, str | None]] | None = None,
) -> Bill:
    if period_ym is None:
        today = date.today()
        period_ym = f"{today.year:04d}-{today.month:02d}"
    bank = BankConfig(
        bank_code=bank_code,
        bank_name=f"{bank_code}-name",
        gmail_filter=f"from:{bank_code.lower()}",
    )
    session.add(bank)
    bill = Bill(
        bank_code=bank_code,
        billing_month=period_ym,
        total_amount=sum(t[0] for t in (txns or [])),
        due_date=date.today() + timedelta(days=20),
        is_paid=False,
    )
    session.add(bill)
    await session.flush()
    for amount, merchant, category in txns or []:
        session.add(
            Transaction(
                bill_id=bill.id,
                trans_date=date.today(),
                merchant=merchant,
                amount=amount,
                currency="TWD",
                category=category,
            )
        )
    await session.commit()
    await session.refresh(bill)
    return bill


async def test_triggers_at_80_percent(db_session: AsyncSession) -> None:
    b = Budget(
        scope=BudgetScope.MONTHLY_TOTAL,
        scope_ref=None,
        amount_minor_units=10000,
        alert_threshold_percent=80,
        enabled=True,
    )
    db_session.add(b)
    await db_session.commit()
    await _seed_bank_bill(db_session, txns=[(8500, "M1", "餐飲")])

    with patch(
        "ccas.scheduler.budget_evaluator.send_message",
        new=AsyncMock(return_value=None),
    ) as mock_send:
        result = await evaluate_budgets(db_session)

    assert result["alerts_triggered"] == 1
    alerts = (await db_session.execute(select(BudgetAlert))).scalars().all()
    assert len(alerts) == 1
    assert alerts[0].threshold_breached_percent == 80
    assert alerts[0].current_amount_minor_units == 8500
    assert mock_send.await_count == 1


async def test_does_not_double_trigger_same_month_same_threshold(
    db_session: AsyncSession,
) -> None:
    b = Budget(
        scope=BudgetScope.MONTHLY_TOTAL,
        amount_minor_units=10000,
        alert_threshold_percent=80,
        enabled=True,
    )
    db_session.add(b)
    await db_session.commit()
    await _seed_bank_bill(db_session, txns=[(8500, "M1", "餐飲")])

    with patch(
        "ccas.scheduler.budget_evaluator.send_message",
        new=AsyncMock(return_value=None),
    ) as mock_send:
        await evaluate_budgets(db_session)
        await evaluate_budgets(db_session)  # second run should be no-op

    alerts = (await db_session.execute(select(BudgetAlert))).scalars().all()
    assert len(alerts) == 1
    assert mock_send.await_count == 1


async def test_disabled_budget_skipped(db_session: AsyncSession) -> None:
    b = Budget(
        scope=BudgetScope.MONTHLY_TOTAL,
        amount_minor_units=10000,
        alert_threshold_percent=80,
        enabled=False,
    )
    db_session.add(b)
    await db_session.commit()
    await _seed_bank_bill(db_session, txns=[(9500, "M1", None)])

    with patch(
        "ccas.scheduler.budget_evaluator.send_message",
        new=AsyncMock(return_value=None),
    ) as mock_send:
        result = await evaluate_budgets(db_session)

    assert result["alerts_triggered"] == 0
    assert mock_send.await_count == 0


async def test_telegram_disabled_does_not_raise(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "")
    from ccas.config import get_settings

    get_settings.cache_clear()  # type: ignore[attr-defined]

    b = Budget(
        scope=BudgetScope.MONTHLY_TOTAL,
        amount_minor_units=10000,
        alert_threshold_percent=80,
        enabled=True,
    )
    db_session.add(b)
    await db_session.commit()
    await _seed_bank_bill(db_session, txns=[(9500, "M1", None)])

    # Should not raise even when telegram disabled
    result = await evaluate_budgets(db_session)
    assert result["alerts_triggered"] == 1
    alerts = (await db_session.execute(select(BudgetAlert))).scalars().all()
    assert len(alerts) == 1  # alert still recorded


async def test_aggregates_multiple_alerts_into_single_message(
    db_session: AsyncSession,
) -> None:
    db_session.add_all(
        [
            Budget(
                scope=BudgetScope.MONTHLY_TOTAL,
                amount_minor_units=10000,
                alert_threshold_percent=80,
                enabled=True,
            ),
            Budget(
                scope=BudgetScope.MONTHLY_BANK,
                scope_ref="CTBC",
                amount_minor_units=5000,
                alert_threshold_percent=80,
                enabled=True,
            ),
        ]
    )
    await db_session.commit()
    await _seed_bank_bill(db_session, bank_code="CTBC", txns=[(8500, "M1", "餐飲")])

    with patch(
        "ccas.scheduler.budget_evaluator.send_message",
        new=AsyncMock(return_value=None),
    ) as mock_send:
        await evaluate_budgets(db_session)

    # 兩個預算都 breach；訊息聚合為單則
    # Budget1 (10000 cap, 8500 → 85%) → 觸發 80% threshold
    # Budget2 (5000 cap, 8500 → 170%) → 觸發 80% + 100% threshold（兩階）
    assert mock_send.await_count == 1
    alerts = (await db_session.execute(select(BudgetAlert))).scalars().all()
    assert len(alerts) == 3


async def test_higher_threshold_triggers_after_lower(
    db_session: AsyncSession,
) -> None:
    """80% 觸發後，當花費再上升超過 100% 時應再觸發 100% threshold."""
    b = Budget(
        scope=BudgetScope.MONTHLY_TOTAL,
        amount_minor_units=10000,
        alert_threshold_percent=80,
        enabled=True,
    )
    db_session.add(b)
    await db_session.commit()
    bill = await _seed_bank_bill(db_session, txns=[(8500, "M1", None)])

    with patch(
        "ccas.scheduler.budget_evaluator.send_message",
        new=AsyncMock(return_value=None),
    ):
        await evaluate_budgets(db_session)

    # 加大消費到 11000 (110%)
    db_session.add(
        Transaction(
            bill_id=bill.id,
            trans_date=date.today(),
            merchant="M2",
            amount=2500,
            currency="TWD",
        )
    )
    await db_session.commit()

    with patch(
        "ccas.scheduler.budget_evaluator.send_message",
        new=AsyncMock(return_value=None),
    ) as mock_send:
        result = await evaluate_budgets(db_session)

    assert result["alerts_triggered"] == 1
    alerts = (
        (await db_session.execute(select(BudgetAlert).order_by(BudgetAlert.id)))
        .scalars()
        .all()
    )
    assert len(alerts) == 2
    assert alerts[0].threshold_breached_percent == 80
    assert alerts[1].threshold_breached_percent == 100
    assert mock_send.await_count == 1
