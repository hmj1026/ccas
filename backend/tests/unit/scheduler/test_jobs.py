"""Reminder and budget scheduler adapters.

Pipeline submission is covered through its shared module and SQLite-backed
scheduler integration tests rather than duplicated session mock call counts.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ccas.scheduler.jobs import (
    run_budget_evaluator_sync,
    run_payment_reminders_sync,
)


def _make_db_mocks(run_obj: object | None = None):
    """建立 async session factory / engine mocks。"""
    session = MagicMock()
    session.commit = AsyncMock()
    session.get = AsyncMock(return_value=run_obj)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    factory = MagicMock(return_value=ctx)
    engine = MagicMock()
    engine.dispose = AsyncMock()
    return factory, engine, session


def _run_reminders(result=None, side_effect=None):
    """以完整 mock 環境執行 run_payment_reminders_sync，回傳觀測點。"""
    factory, engine, session = _make_db_mocks()
    reminders = AsyncMock(return_value=result, side_effect=side_effect)
    with (
        patch("ccas.scheduler.reminders.send_payment_reminders", reminders),
        patch("ccas.storage.database.get_session_factory", return_value=factory),
        patch("ccas.storage.database.get_engine", return_value=engine),
    ):
        if side_effect is not None:
            with pytest.raises(type(side_effect)):
                run_payment_reminders_sync()
            return {"engine": engine, "session": session, "reminders": reminders}
        out = run_payment_reminders_sync()
        return {
            "result": out,
            "engine": engine,
            "session": session,
            "reminders": reminders,
        }


class TestRunPaymentRemindersSync:
    """同步封裝：開 session → 呼叫 send_payment_reminders → dispose engine。"""

    def test_returns_result_and_disposes_engine(self):
        env = _run_reminders(result={"sent": 2, "skipped": 1})
        assert env["result"] == {"sent": 2, "skipped": 1}
        env["reminders"].assert_awaited_once_with(env["session"])
        env["engine"].dispose.assert_awaited_once()

    def test_reraises_on_failure(self):
        env = _run_reminders(side_effect=RuntimeError("reminder boom"))
        # 失敗發生在 dispose 之前 → engine 未被 dispose
        env["engine"].dispose.assert_not_awaited()


def _run_budget(result=None, side_effect=None):
    """以完整 mock 環境執行 run_budget_evaluator_sync，回傳觀測點。"""
    factory, engine, session = _make_db_mocks()
    evaluator = AsyncMock(return_value=result, side_effect=side_effect)
    with (
        patch("ccas.scheduler.budget_evaluator.evaluate_budgets", evaluator),
        patch("ccas.storage.database.get_session_factory", return_value=factory),
        patch("ccas.storage.database.get_engine", return_value=engine),
    ):
        if side_effect is not None:
            with pytest.raises(type(side_effect)):
                run_budget_evaluator_sync()
            return {"engine": engine, "session": session, "evaluator": evaluator}
        out = run_budget_evaluator_sync()
        return {
            "result": out,
            "engine": engine,
            "session": session,
            "evaluator": evaluator,
        }


class TestRunBudgetEvaluatorSync:
    """同步封裝：開 session → 呼叫 evaluate_budgets → dispose engine。"""

    def test_returns_result_and_disposes_engine(self):
        env = _run_budget(result={"alerts_triggered": 3, "skipped": 4})
        assert env["result"] == {"alerts_triggered": 3, "skipped": 4}
        env["evaluator"].assert_awaited_once_with(env["session"])
        env["engine"].dispose.assert_awaited_once()

    def test_reraises_on_failure(self):
        env = _run_budget(side_effect=RuntimeError("budget boom"))
        env["engine"].dispose.assert_not_awaited()
