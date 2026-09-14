"""Integration tests for Agent datetime and discovery version contracts."""

from __future__ import annotations

import asyncio
import tempfile
from datetime import datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ccas import __version__
from ccas.storage.models import PipelineRun, PipelineRunStatus
from tests.integration import test_agent_cli as cli_wire
from tests.integration import test_agent_mcp as mcp_wire

_DATETIME_FIELDS = ("started_at", "completed_at", "created_at", "updated_at")


async def _seed_pipeline_run(db_path: Path) -> None:
    engine = create_async_engine(cli_wire._database_url(db_path))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        timestamp = datetime(2026, 4, 1, 12, 0, 0)
        session.add(
            PipelineRun(
                id="run-datetime",
                job_id="job-datetime",
                status=PipelineRunStatus.SUCCEEDED,
                triggered_by="test",
                params={},
                current_stage=None,
                current_stage_processed=0,
                current_stage_total=0,
                stage_summary=[],
                error_message=None,
                started_at=timestamp,
                completed_at=timestamp,
                created_at=timestamp,
                updated_at=timestamp,
            )
        )
        await session.commit()
    await engine.dispose()


def _assert_strict_utc_datetime(value: str) -> None:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() is not None
    assert value.endswith("Z")


def test_pipeline_status_returns_strict_utc_datetimes_and_release_version() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path = root / "pipeline-datetime.sqlite3"
        asyncio.run(mcp_wire._create_schema(db_path))
        asyncio.run(_seed_pipeline_run(db_path))

        with mcp_wire._McpProcess(db_path, root) as server:
            discovery = server.request(mcp_wire._request("server/discover", 1))
            server.request(mcp_wire._request("tools/list", 2))
            result = server.request(mcp_wire._tool_call("pipeline_status", 3, {}))[
                "result"
            ]

        assert (
            discovery["result"]["_meta"]["io.modelcontextprotocol/serverInfo"][
                "version"
            ]
            == __version__
        )
        assert result["resultType"] == "complete"
        values = result["structuredContent"]["data"]
        assert all(values[field].endswith("Z") for field in _DATETIME_FIELDS)
        for field in _DATETIME_FIELDS:
            _assert_strict_utc_datetime(values[field])


def test_bill_agent_tools_return_created_at_with_utc_suffix() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path = root / "bill-datetime.sqlite3"
        asyncio.run(mcp_wire._create_schema(db_path))
        bill_id = asyncio.run(mcp_wire._seed_bill(db_path))

        with mcp_wire._McpProcess(db_path, root) as server:
            server.request(mcp_wire._request("server/discover", 1))
            server.request(mcp_wire._request("tools/list", 2))
            results = {
                "list_bills": server.request(mcp_wire._tool_call("list_bills", 3, {}))[
                    "result"
                ],
                "get_bill": server.request(
                    mcp_wire._tool_call("get_bill", 4, {"bill_id": bill_id})
                )["result"],
                "get_payment_due": server.request(
                    mcp_wire._tool_call("get_payment_due", 5, {})
                )["result"],
            }

        bills = {
            "list_bills": results["list_bills"]["structuredContent"]["data"][0],
            "get_bill": results["get_bill"]["structuredContent"]["data"],
            "get_payment_due": results["get_payment_due"]["structuredContent"]["data"][
                0
            ],
        }
        for result in results.values():
            assert result["resultType"] == "complete"
        for bill in bills.values():
            _assert_strict_utc_datetime(bill["created_at"])
