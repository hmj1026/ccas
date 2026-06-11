"""Alembic up/down/up verification for ``f3a9d8c1b2e4`` (budget NTD rename).

Verifies against a scratch SQLite file that:

- ``upgrade head`` renames ``budgets.amount_minor_units`` → ``amount_ntd``
  and ``budget_alerts.current_amount_minor_units`` → ``current_amount_ntd``
- ``downgrade -1`` reverses both renames
- a second ``upgrade head`` re-applies cleanly (idempotent round-trip)
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from alembic import command

_BACKEND_ROOT = Path(__file__).resolve().parents[3]


def _columns(db_path: Path, table: str) -> set[str]:
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        return {col["name"] for col in inspect(engine).get_columns(table)}
    finally:
        engine.dispose()


@pytest.fixture
def alembic_scratch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[tuple[Config, Path], None, None]:
    """Alembic config pointed at a scratch SQLite DB via DATABASE_URL."""
    db_path = tmp_path / "scratch.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    from ccas.config import get_settings

    get_settings.cache_clear()  # type: ignore[attr-defined]
    cfg = Config(str(_BACKEND_ROOT / "alembic.ini"))
    yield cfg, db_path
    get_settings.cache_clear()  # type: ignore[attr-defined]


def test_budget_amount_ntd_rename_up_down_up(
    alembic_scratch: tuple[Config, Path],
) -> None:
    cfg, db_path = alembic_scratch

    # up: head schema uses the NTD column names
    command.upgrade(cfg, "head")
    budgets = _columns(db_path, "budgets")
    alerts = _columns(db_path, "budget_alerts")
    assert "amount_ntd" in budgets
    assert "amount_minor_units" not in budgets
    assert "current_amount_ntd" in alerts
    assert "current_amount_minor_units" not in alerts

    # down: rename reversed on both tables
    command.downgrade(cfg, "-1")
    budgets = _columns(db_path, "budgets")
    alerts = _columns(db_path, "budget_alerts")
    assert "amount_minor_units" in budgets
    assert "amount_ntd" not in budgets
    assert "current_amount_minor_units" in alerts
    assert "current_amount_ntd" not in alerts

    # up again: round-trip re-applies cleanly
    command.upgrade(cfg, "head")
    assert "amount_ntd" in _columns(db_path, "budgets")
    assert "current_amount_ntd" in _columns(db_path, "budget_alerts")
