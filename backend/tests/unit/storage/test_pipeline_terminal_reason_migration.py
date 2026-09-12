"""Regression coverage for the pipeline terminal-reason migration round trip."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from alembic import command

_BACKEND_ROOT = Path(__file__).resolve().parents[3]
_OLD_HEAD = "7f3ae66246a3"
_TERMINAL_REASON_REVISION = "b72e619af430"


@pytest.fixture
def alembic_scratch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[tuple[Config, Path], None, None]:
    db_path = tmp_path / "pipeline-terminal-reason.sqlite3"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")

    from ccas.config import get_settings

    get_settings.cache_clear()  # type: ignore[attr-defined]
    config = Config(str(_BACKEND_ROOT / "alembic.ini"))
    try:
        yield config, db_path
    finally:
        get_settings.cache_clear()  # type: ignore[attr-defined]


def _master_sql(db_path: Path, object_type: str, name: str) -> str | None:
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        with engine.connect() as connection:
            return connection.execute(
                text(
                    "SELECT sql FROM sqlite_master "
                    "WHERE type = :object_type AND name = :name"
                ),
                {"object_type": object_type, "name": name},
            ).scalar_one_or_none()
    finally:
        engine.dispose()


def _column_names(db_path: Path, table_name: str) -> set[str]:
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        return {column["name"] for column in inspect(engine).get_columns(table_name)}
    finally:
        engine.dispose()


def _insert_legacy_run(db_path: Path) -> None:
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO pipeline_runs "
                    "(id, job_id, status, triggered_by, params, "
                    "current_stage_processed, current_stage_total, stage_summary, "
                    "created_at, updated_at) "
                    "VALUES (:id, :job_id, :status, :triggered_by, :params, "
                    ":processed, :total, :summary, :created_at, :updated_at)"
                ),
                {
                    "id": "legacy-run",
                    "job_id": "legacy-job",
                    "status": "failed",
                    "triggered_by": "api",
                    "params": "{}",
                    "processed": 0,
                    "total": 0,
                    "summary": "[]",
                    "created_at": "2026-09-01 00:00:00",
                    "updated_at": "2026-09-01 00:00:00",
                },
            )
    finally:
        engine.dispose()


def _legacy_terminal_reason(db_path: Path) -> str | None:
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        with engine.connect() as connection:
            return connection.execute(
                text(
                    "SELECT terminal_reason FROM pipeline_runs WHERE id = 'legacy-run'"
                )
            ).scalar_one()
    finally:
        engine.dispose()


def test_pipeline_terminal_reason_upgrade_downgrade_reupgrade_preserves_sqlite_objects(
    alembic_scratch: tuple[Config, Path],
) -> None:
    config, db_path = alembic_scratch

    command.upgrade(config, _OLD_HEAD)
    _insert_legacy_run(db_path)

    command.upgrade(config, _TERMINAL_REASON_REVISION)
    assert "terminal_reason" in _column_names(db_path, "pipeline_runs")
    assert _legacy_terminal_reason(db_path) is None

    command.downgrade(config, _OLD_HEAD)
    assert "terminal_reason" not in _column_names(db_path, "pipeline_runs")
    assert _master_sql(db_path, "trigger", "pipeline_runs_updated_at_trigger")
    index_sql = _master_sql(db_path, "index", "ix_pipeline_runs_created_at_desc")
    assert index_sql is not None
    assert "CREATED_AT DESC" in index_sql.upper()

    command.upgrade(config, _TERMINAL_REASON_REVISION)
    assert "terminal_reason" in _column_names(db_path, "pipeline_runs")
    assert _legacy_terminal_reason(db_path) is None
    assert _master_sql(db_path, "trigger", "pipeline_runs_updated_at_trigger")
    reupgraded_index_sql = _master_sql(
        db_path, "index", "ix_pipeline_runs_created_at_desc"
    )
    assert reupgraded_index_sql is not None
    assert "CREATED_AT DESC" in reupgraded_index_sql.upper()
