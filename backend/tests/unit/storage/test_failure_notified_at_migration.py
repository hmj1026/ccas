"""Backfill and round-trip checks for staged_attachments.failure_notified_at."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from alembic import command

_BACKEND_ROOT = Path(__file__).resolve().parents[3]
_OLD_HEAD = "d4e7f2a1b9c3"
_REVISION = "a8c3f1d7e520"


@pytest.fixture
def alembic_scratch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[tuple[Config, Path], None, None]:
    db_path = tmp_path / "failure-notified-at.sqlite3"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    from ccas.config import get_settings

    get_settings.cache_clear()  # type: ignore[attr-defined]
    config = Config(str(_BACKEND_ROOT / "alembic.ini"))
    try:
        yield config, db_path
    finally:
        get_settings.cache_clear()  # type: ignore[attr-defined]


def _column_names(db_path: Path) -> set[str]:
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        return {c["name"] for c in inspect(engine).get_columns("staged_attachments")}
    finally:
        engine.dispose()


def _insert_attachment(db_path: Path, message_id: str, status: str) -> None:
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO staged_attachments "
                    "(bank_code, gmail_message_id, gmail_attachment_id, "
                    "gmail_part_id, message_date, original_filename, status, "
                    "source_type, created_at) "
                    "VALUES ('CTBC', :mid, 'att', '1', '2026-05-01 00:00:00', "
                    "'s.pdf', :status, 'attachment', '2026-05-01 00:00:00')"
                ),
                {"mid": message_id, "status": status},
            )
    finally:
        engine.dispose()


def test_backfills_existing_parse_failures_and_round_trips(
    alembic_scratch: tuple[Config, Path],
) -> None:
    config, db_path = alembic_scratch
    command.upgrade(config, _OLD_HEAD)
    _insert_attachment(db_path, "failed", "parse_failed")
    _insert_attachment(db_path, "parsed", "parsed")

    command.upgrade(config, _REVISION)

    assert "failure_notified_at" in _column_names(db_path)
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        with engine.connect() as connection:
            rows: dict[str, object] = {
                row[0]: row[1]
                for row in connection.execute(
                    text(
                        "SELECT gmail_message_id, failure_notified_at "
                        "FROM staged_attachments"
                    )
                )
            }
    finally:
        engine.dispose()
    # 既有解析失敗視為已知，不在升級後的第一次執行全部重新通知。
    assert rows["failed"] is not None
    assert rows["parsed"] is None

    command.downgrade(config, _OLD_HEAD)
    assert "failure_notified_at" not in _column_names(db_path)
    command.upgrade(config, "head")
    assert "failure_notified_at" in _column_names(db_path)
