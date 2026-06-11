"""Unit tests for ``ccas.scheduler.budget_evaluator``.

涵蓋兩類：

1. **Pure helpers**：``_current_year_month`` / ``_scope_label`` /
   ``_format_aggregated_message`` 不需 DB 即可驗。
2. **End-to-end with in-memory SQLite**：``evaluate_budgets`` 端對端
   驗證 80% / 100% threshold ladder、去重、Telegram disabled 行為。
   這些案例在 ``tests/integration/`` 也有覆蓋；放在 unit 是為了讓
   pre-push 的 ``tests/unit/ --cov-fail-under=70`` gate 也納入這支
   核心模組的覆蓋率（不必下放到 router 層即能捕捉 evaluator regression）。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ccas.scheduler.budget_evaluator import (
    _current_year_month,
    _format_aggregated_message,
    _scope_label,
    evaluate_budgets,
)
from ccas.storage.models import (
    BankConfig,
    Base,
    Bill,
    Budget,
    BudgetAlert,
    BudgetScope,
    Transaction,
)

# -- Pure helpers --


class TestCurrentYearMonth:
    def test_pads_single_digit_month(self):
        assert _current_year_month(date(2026, 3, 15)) == "2026-03"

    def test_handles_december(self):
        assert _current_year_month(date(2026, 12, 31)) == "2026-12"

    def test_defaults_to_today(self):
        # Just smoke — should be in YYYY-MM shape.
        out = _current_year_month()
        assert len(out) == 7 and out[4] == "-"


class TestScopeLabel:
    def test_monthly_total(self):
        b = Budget(
            scope=BudgetScope.MONTHLY_TOTAL,
            scope_ref=None,
            amount_ntd=1000,
            alert_threshold_percent=80,
            enabled=True,
        )
        assert _scope_label(b) == "整月支出"

    def test_monthly_category(self):
        b = Budget(
            scope=BudgetScope.MONTHLY_CATEGORY,
            scope_ref="餐飲",
            amount_ntd=1000,
            alert_threshold_percent=80,
            enabled=True,
        )
        assert _scope_label(b) == "類別「餐飲」"

    def test_monthly_bank(self):
        b = Budget(
            scope=BudgetScope.MONTHLY_BANK,
            scope_ref="CTBC",
            amount_ntd=1000,
            alert_threshold_percent=80,
            enabled=True,
        )
        assert _scope_label(b) == "銀行「CTBC」"


class TestFormatAggregatedMessage:
    def test_includes_period_header_and_each_alert_line(self):
        b1 = Budget(
            scope=BudgetScope.MONTHLY_TOTAL,
            scope_ref=None,
            amount_ntd=10000,
            alert_threshold_percent=80,
            enabled=True,
        )
        b2 = Budget(
            scope=BudgetScope.MONTHLY_CATEGORY,
            scope_ref="交通",
            amount_ntd=5000,
            alert_threshold_percent=80,
            enabled=True,
        )
        a1 = BudgetAlert(
            budget_id=1,
            period_year_month="2026-05",
            threshold_breached_percent=80,
            current_amount_ntd=8500,
            triggered_at=datetime.now(UTC),
        )
        a2 = BudgetAlert(
            budget_id=2,
            period_year_month="2026-05",
            threshold_breached_percent=100,
            current_amount_ntd=5200,
            triggered_at=datetime.now(UTC),
        )
        msg = _format_aggregated_message("2026-05", [(b1, a1), (b2, a2)])
        assert "預算超支警示（2026-05）" in msg
        assert "整月支出" in msg
        assert "8,500" in msg and "10,000" in msg and "80%" in msg
        assert "類別「交通」" in msg
        assert "5,200" in msg and "5,000" in msg and "100%" in msg


# -- evaluate_budgets end-to-end (in-memory) --


@pytest.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    """Per-test in-memory async SQLite session."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


def _today_period() -> tuple[date, str]:
    today = date.today()
    return today, f"{today.year:04d}-{today.month:02d}"


async def _seed_bill_with_txns(
    session: AsyncSession,
    *,
    period_ym: str,
    bank_code: str = "CTBC",
    txns: list[tuple[int, str | None]] | None = None,
) -> Bill:
    """Seed a bill + txns for the given period. txns: (amount in NTD 元, category)."""
    session.add(
        BankConfig(
            bank_code=bank_code,
            bank_name=f"{bank_code}-name",
            gmail_filter=f"from:{bank_code.lower()}",
        )
    )
    bill = Bill(
        bank_code=bank_code,
        billing_month=period_ym,
        total_amount=sum((t[0] for t in txns or []), 0),
        due_date=date.today() + timedelta(days=10),
        is_paid=False,
    )
    session.add(bill)
    await session.flush()
    for amount, category in txns or []:
        session.add(
            Transaction(
                bill_id=bill.id,
                trans_date=date.today(),
                merchant=f"M-{amount}",
                amount=amount,
                currency="TWD",
                category=category,
            )
        )
    await session.commit()
    await session.refresh(bill)
    return bill


@patch("ccas.scheduler.budget_evaluator.send_message", new_callable=AsyncMock)
async def test_triggers_alert_at_80_percent(mock_send, session: AsyncSession):
    today, period = _today_period()
    await _seed_bill_with_txns(session, period_ym=period, txns=[(8500, "餐飲")])

    session.add(
        Budget(
            scope=BudgetScope.MONTHLY_TOTAL,
            scope_ref=None,
            amount_ntd=10000,
            alert_threshold_percent=80,
            enabled=True,
        )
    )
    await session.commit()

    out = await evaluate_budgets(session, today=today)
    assert out["alerts_triggered"] == 1
    rows = (
        await session.execute(
            BudgetAlert.__table__.select(),
        )
    ).all()
    assert len(rows) == 1
    mock_send.assert_called_once()


@patch("ccas.scheduler.budget_evaluator.send_message", new_callable=AsyncMock)
async def test_does_not_duplicate_alert_for_same_threshold(
    mock_send, session: AsyncSession
):
    today, period = _today_period()
    await _seed_bill_with_txns(session, period_ym=period, txns=[(8500, "餐飲")])

    session.add(
        Budget(
            scope=BudgetScope.MONTHLY_TOTAL,
            scope_ref=None,
            amount_ntd=10000,
            alert_threshold_percent=80,
            enabled=True,
        )
    )
    await session.commit()

    await evaluate_budgets(session, today=today)
    out2 = await evaluate_budgets(session, today=today)
    assert out2["alerts_triggered"] == 0
    rows = (await session.execute(BudgetAlert.__table__.select())).all()
    assert len(rows) == 1


@patch("ccas.scheduler.budget_evaluator.send_message", new_callable=AsyncMock)
async def test_triggers_higher_tier_after_breaching_100_percent(
    mock_send, session: AsyncSession
):
    today, period = _today_period()
    bill = await _seed_bill_with_txns(session, period_ym=period, txns=[(8500, "餐飲")])

    session.add(
        Budget(
            scope=BudgetScope.MONTHLY_TOTAL,
            scope_ref=None,
            amount_ntd=10000,
            alert_threshold_percent=80,
            enabled=True,
        )
    )
    await session.commit()

    # First run triggers 80%
    out1 = await evaluate_budgets(session, today=today)
    assert out1["alerts_triggered"] == 1

    # Add more spend to cross 100%
    session.add(
        Transaction(
            bill_id=bill.id,
            trans_date=today,
            merchant="big",
            amount=2000,
            currency="TWD",
            category="餐飲",
        )
    )
    await session.commit()

    out2 = await evaluate_budgets(session, today=today)
    assert out2["alerts_triggered"] == 1
    rows = (await session.execute(BudgetAlert.__table__.select())).all()
    # 80% + 100% — both recorded
    assert len(rows) == 2


@patch("ccas.scheduler.budget_evaluator.send_message", new_callable=AsyncMock)
async def test_skips_disabled_budgets_and_zero_amount(mock_send, session: AsyncSession):
    today, period = _today_period()
    await _seed_bill_with_txns(session, period_ym=period, txns=[(9000, None)])

    session.add_all(
        [
            Budget(
                scope=BudgetScope.MONTHLY_TOTAL,
                scope_ref=None,
                amount_ntd=10000,
                alert_threshold_percent=80,
                enabled=False,
            ),
            Budget(
                scope=BudgetScope.MONTHLY_TOTAL,
                scope_ref=None,
                amount_ntd=0,
                alert_threshold_percent=80,
                enabled=True,
            ),
        ]
    )
    await session.commit()

    out = await evaluate_budgets(session, today=today)
    assert out["alerts_triggered"] == 0
    # zero-amount budget counted as skipped
    assert out["skipped"] == 1
    mock_send.assert_not_called()


@patch("ccas.scheduler.budget_evaluator.send_message", new_callable=AsyncMock)
async def test_does_not_raise_when_telegram_disabled(
    mock_send, session: AsyncSession, monkeypatch
):
    today, period = _today_period()
    await _seed_bill_with_txns(session, period_ym=period, txns=[(9000, "餐飲")])

    session.add(
        Budget(
            scope=BudgetScope.MONTHLY_CATEGORY,
            scope_ref="餐飲",
            amount_ntd=10000,
            alert_threshold_percent=80,
            enabled=True,
        )
    )
    await session.commit()

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "")
    from ccas.config import get_settings

    get_settings.cache_clear()

    out = await evaluate_budgets(session, today=today)
    assert out["alerts_triggered"] == 1
    mock_send.assert_not_called()


@patch(
    "ccas.scheduler.budget_evaluator.send_message",
    new_callable=AsyncMock,
    side_effect=RuntimeError("boom"),
)
async def test_swallows_telegram_send_errors(mock_send, session: AsyncSession):
    today, period = _today_period()
    await _seed_bill_with_txns(session, period_ym=period, txns=[(9000, "餐飲")])

    session.add(
        Budget(
            scope=BudgetScope.MONTHLY_TOTAL,
            scope_ref=None,
            amount_ntd=10000,
            alert_threshold_percent=80,
            enabled=True,
        )
    )
    await session.commit()

    # send_message raises but evaluate_budgets must not propagate
    out = await evaluate_budgets(session, today=today)
    assert out["alerts_triggered"] == 1
    mock_send.assert_called_once()


@patch("ccas.scheduler.budget_evaluator.send_message", new_callable=AsyncMock)
async def test_aggregates_alerts_from_multiple_budgets_into_one_message(
    mock_send, session: AsyncSession
):
    today, period = _today_period()
    await _seed_bill_with_txns(
        session,
        period_ym=period,
        bank_code="CTBC",
        txns=[(7500, "餐飲"), (4500, "交通")],
    )

    session.add_all(
        [
            Budget(
                scope=BudgetScope.MONTHLY_TOTAL,
                scope_ref=None,
                amount_ntd=10000,
                alert_threshold_percent=80,
                enabled=True,
            ),
            Budget(
                scope=BudgetScope.MONTHLY_CATEGORY,
                scope_ref="交通",
                amount_ntd=5000,
                alert_threshold_percent=80,
                enabled=True,
            ),
        ]
    )
    await session.commit()

    out = await evaluate_budgets(session, today=today)
    # Total 12000：MONTHLY_TOTAL 80%(8000)+100%(10000) 雙觸發；交通 4500 跨 80%
    assert out["alerts_triggered"] == 3
    # Single send_message call combining all alerts
    assert mock_send.call_count == 1
    text = mock_send.call_args.args[2]
    assert "整月支出" in text and "類別「交通」" in text
