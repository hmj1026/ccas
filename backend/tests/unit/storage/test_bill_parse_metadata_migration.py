"""Round-trip and nullability checks for bill parse metadata migration."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from alembic import command

_BACKEND_ROOT = Path(__file__).resolve().parents[3]
_OLD_HEAD = "b72e619af430"
_REVISION = "d4e7f2a1b9c3"


@pytest.fixture
def alembic_scratch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[tuple[Config, Path], None, None]:
    db_path = tmp_path / "bill-parse-metadata.sqlite3"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    from ccas.config import get_settings

    get_settings.cache_clear()  # type: ignore[attr-defined]
    config = Config(str(_BACKEND_ROOT / "alembic.ini"))
    try:
        yield config, db_path
    finally:
        get_settings.cache_clear()  # type: ignore[attr-defined]


def _columns(db_path: Path) -> list[Any]:
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        return inspect(engine).get_columns("bills")
    finally:
        engine.dispose()


def test_bill_parse_metadata_is_nullable_and_round_trips(
    alembic_scratch: tuple[Config, Path],
) -> None:
    config, db_path = alembic_scratch
    command.upgrade(config, _OLD_HEAD)

    engine = create_engine(f"sqlite:///{db_path}")
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO bills "
                    "(bank_code, billing_month, total_amount, due_date, "
                    "due_date_estimated, is_paid, is_notified, created_at) "
                    "VALUES ('CTBC', '2026-03', 100, '2026-04-15', 0, 0, 1, "
                    "'2026-09-13 00:00:00')"
                )
            )
    finally:
        engine.dispose()

    command.upgrade(config, _REVISION)
    columns = {column["name"]: column for column in _columns(db_path)}
    assert {
        "parse_method",
        "parse_confidence",
        "needs_review",
        "review_reasons",
    } <= set(columns)
    assert all(
        columns[name]["nullable"] is True
        for name in (
            "parse_method",
            "parse_confidence",
            "needs_review",
            "review_reasons",
        )
    )

    engine = create_engine(f"sqlite:///{db_path}")
    try:
        with engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT parse_method, parse_confidence, needs_review, "
                    "review_reasons "
                    "FROM bills WHERE bank_code = 'CTBC'"
                )
            ).one()
            assert row == (None, None, None, None)
    finally:
        engine.dispose()

    command.downgrade(config, _OLD_HEAD)
    assert not (
        {column["name"] for column in _columns(db_path)}
        & {"parse_method", "parse_confidence", "needs_review", "review_reasons"}
    )
    command.upgrade(config, "head")
    assert {"parse_method", "parse_confidence", "needs_review", "review_reasons"} <= {
        column["name"] for column in _columns(db_path)
    }
