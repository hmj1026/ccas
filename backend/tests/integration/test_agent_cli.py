"""Contract tests for the read-only Agent CLI adapter."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ccas.storage.models import Base, Bill

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_SOURCE_ROOT = _BACKEND_ROOT / "src"
_READ_COMMANDS = (
    "list-bills",
    "get-bill",
    "query-transactions",
    "get-payment-due",
    "budget-status",
    "pipeline-status",
)
_WRITE_COMMANDS = (
    "mark-bill-paid",
    "set-payment-status",
    "override-transaction-category",
    "trigger-ingest",
    "retry-parse",
)


def _database_url(db_path: Path) -> str:
    return f"sqlite+aiosqlite:///{db_path}"


def _test_environment(
    db_path: Path,
    tmp_path: Path,
    *,
    write_enabled: bool = False,
) -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(_SOURCE_ROOT),
        "PYTHONUNBUFFERED": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "DATABASE_URL": _database_url(db_path),
        "TELEGRAM_BOT_TOKEN": "test",
        "TELEGRAM_CHAT_ID": "123",
        "API_TOKEN": "test",
        "AGENT_WRITE_ENABLED": str(write_enabled).lower(),
        "MASTER_KEY_PATH": str(tmp_path / "master.key"),
        "GMAIL_CREDENTIALS_PATH": str(tmp_path / "credentials.json"),
        "GMAIL_TOKEN_PATH": str(tmp_path / "token.json"),
        "STAGING_DIR": str(tmp_path / "staging"),
        "LOG_DIR": str(tmp_path / "logs"),
    }


async def _create_schema(db_path: Path) -> None:
    engine = create_async_engine(_database_url(db_path))
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()


async def _seed_bill(db_path: Path) -> int:
    engine = create_async_engine(_database_url(db_path))
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        bill = Bill(
            bank_code="CTBC",
            billing_month="2026-03",
            total_amount=1234,
            due_date=date(2026, 4, 15),
            is_paid=False,
        )
        session.add(bill)
        await session.commit()
        bill_id = bill.id
    await engine.dispose()
    return bill_id


def _run_cli(
    db_path: Path,
    tmp_path: Path,
    args: list[str],
    *,
    write_enabled: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "ccas.cli", *args],
        cwd=_BACKEND_ROOT,
        env=_test_environment(
            db_path,
            tmp_path,
            write_enabled=write_enabled,
        ),
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )


def test_cli_list_bills_defaults_to_json_and_supports_json_and_table(
    tmp_path: Path,
):
    db_path = tmp_path / "cli.sqlite3"
    asyncio.run(_create_schema(db_path))
    asyncio.run(_seed_bill(db_path))

    default_result = _run_cli(db_path, tmp_path, ["list-bills"])
    json_result = _run_cli(db_path, tmp_path, ["list-bills", "--format", "json"])
    table_result = _run_cli(db_path, tmp_path, ["list-bills", "--format", "table"])

    assert default_result.returncode == 0, default_result.stderr
    assert json_result.returncode == 0, json_result.stderr
    assert table_result.returncode == 0, table_result.stderr
    default_payload = json.loads(default_result.stdout)
    json_payload = json.loads(json_result.stdout)
    assert default_payload == json_payload
    assert "jsonrpc" not in default_payload
    assert "CTBC" in table_result.stdout
    assert "2026-03" in table_result.stdout


def test_cli_missing_bill_returns_nonzero_error(tmp_path: Path):
    db_path = tmp_path / "cli.sqlite3"
    asyncio.run(_create_schema(db_path))

    result = _run_cli(db_path, tmp_path, ["get-bill", "--bill-id", "9999"])

    assert result.returncode != 0
    error_output = f"{result.stdout}\n{result.stderr}".lower()
    assert "resource_not_found" in error_output or "not found" in error_output


@pytest.mark.parametrize("write_enabled", [False, True])
def test_cli_hides_write_commands_regardless_of_flag(
    tmp_path: Path,
    write_enabled: bool,
):
    db_path = tmp_path / f"cli-{write_enabled}.sqlite3"
    asyncio.run(_create_schema(db_path))

    result = _run_cli(
        db_path,
        tmp_path,
        ["--help"],
        write_enabled=write_enabled,
    )

    assert result.returncode == 0, result.stderr
    for command in _READ_COMMANDS:
        assert command in result.stdout
    for command in _WRITE_COMMANDS:
        assert command not in result.stdout
