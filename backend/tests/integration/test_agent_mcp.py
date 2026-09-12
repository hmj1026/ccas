"""Wire-contract tests for the read-only stdio MCP server."""

from __future__ import annotations

import asyncio
import json
import os
import select as io_select
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

import jsonschema
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ccas.storage.models import Base, Bill

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_SOURCE_ROOT = _BACKEND_ROOT / "src"
_PROTOCOL_VERSION = "2026-07-28"
_RESPONSE_TIMEOUT_SECONDS = 5
_READ_TOOLS = (
    "list_bills",
    "get_bill",
    "query_transactions",
    "get_payment_due",
    "budget_status",
    "pipeline_status",
)


def _database_url(db_path: Path) -> str:
    return f"sqlite+aiosqlite:///{db_path}"


def _test_environment(db_path: Path, tmp_path: Path) -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(_SOURCE_ROOT),
        "PYTHONUNBUFFERED": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "DATABASE_URL": _database_url(db_path),
        "TELEGRAM_BOT_TOKEN": "test",
        "TELEGRAM_CHAT_ID": "123",
        "API_TOKEN": "test",
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


async def _bill_exists(db_path: Path, bill_id: int) -> bool:
    engine = create_async_engine(_database_url(db_path))
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        exists = (
            await session.execute(select(Bill.id).where(Bill.id == bill_id))
        ).scalar_one_or_none()
    await engine.dispose()
    return exists == bill_id


def _metadata(protocol_version: str = _PROTOCOL_VERSION) -> dict[str, Any]:
    return {
        "io.modelcontextprotocol/protocolVersion": protocol_version,
        "io.modelcontextprotocol/clientCapabilities": {},
    }


def _request(
    method: str,
    request_id: int,
    *,
    params: dict[str, Any] | None = None,
    protocol_version: str = _PROTOCOL_VERSION,
) -> dict[str, Any]:
    request_params = dict(params or {})
    request_params["_meta"] = _metadata(protocol_version)
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": request_params,
    }


def _tool_call(
    tool_name: str,
    request_id: int,
    arguments: dict[str, Any] | None = None,
    *,
    protocol_version: str = _PROTOCOL_VERSION,
) -> dict[str, Any]:
    return _request(
        "tools/call",
        request_id,
        params={"name": tool_name, "arguments": arguments or {}},
        protocol_version=protocol_version,
    )


class _McpProcess:
    def __init__(self, db_path: Path, tmp_path: Path) -> None:
        self._process = subprocess.Popen(
            [sys.executable, "-m", "ccas.mcp"],
            cwd=_BACKEND_ROOT,
            env=_test_environment(db_path, tmp_path),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._closed = False
        self._stderr_text = ""

    def request(self, message: dict[str, Any]) -> dict[str, Any]:
        return self.raw_line(json.dumps(message, separators=(",", ":")))

    def raw_line(self, line: str) -> dict[str, Any]:
        assert self._process.stdin is not None
        assert self._process.stdout is not None
        self._process.stdin.write(line.rstrip("\n") + "\n")
        self._process.stdin.flush()

        ready, _, _ = io_select.select(
            [self._process.stdout], [], [], _RESPONSE_TIMEOUT_SECONDS
        )
        assert ready, "MCP server did not return a response within 5 seconds"
        line = self._process.stdout.readline()
        if not line:
            stderr = ""
            if self._process.poll() is not None and self._process.stderr is not None:
                stderr = self._process.stderr.read()
            raise AssertionError(
                "MCP server closed stdout before returning a response; "
                f"stderr={stderr!r}"
            )
        try:
            response = json.loads(line)
        except json.JSONDecodeError as exc:
            raise AssertionError(
                f"stdout contained non-JSON MCP output: {line!r}"
            ) from exc
        assert isinstance(response, dict)
        return response

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._process.stdin is not None and not self._process.stdin.closed:
            self._process.stdin.close()
        try:
            self._process.wait(timeout=_RESPONSE_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait(timeout=_RESPONSE_TIMEOUT_SECONDS)
            raise AssertionError("MCP server did not exit promptly after stdin EOF")

        if self._process.stdout is not None:
            trailing_lines = self._process.stdout.read().splitlines()
            for line in trailing_lines:
                try:
                    json.loads(line)
                except json.JSONDecodeError as exc:
                    raise AssertionError(
                        f"stdout contained non-JSON MCP output: {line!r}"
                    ) from exc
        if self._process.stderr is not None:
            self._stderr_text = self._process.stderr.read()

    @property
    def stderr_text(self) -> str:
        assert self._closed
        return self._stderr_text

    def __enter__(self) -> _McpProcess:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def test_mcp_discovery_and_tools_list_expose_six_validated_read_tools(
    tmp_path: Path,
):
    db_path = tmp_path / "mcp.sqlite3"
    asyncio.run(_create_schema(db_path))

    with _McpProcess(db_path, tmp_path) as server:
        discovery = server.request(_request("server/discover", 1))
        discovery_result = discovery["result"]
        assert discovery_result["resultType"] == "complete"
        assert _PROTOCOL_VERSION in discovery_result["supportedVersions"]
        assert "tools" in discovery_result["capabilities"]
        assert "listChanged" not in discovery_result["capabilities"]["tools"]
        server_info = discovery_result["_meta"]["io.modelcontextprotocol/serverInfo"]
        assert server_info["name"]
        assert server_info["version"]
        assert "serverInfo" not in discovery_result

        listed = server.request(_request("tools/list", 2))["result"]
        assert listed["resultType"] == "complete"
        tools = listed["tools"]
        assert [tool["name"] for tool in tools] == list(_READ_TOOLS)
        for tool in tools:
            assert tool["description"]
            jsonschema.Draft202012Validator.check_schema(tool["inputSchema"])
            jsonschema.Draft202012Validator.check_schema(tool["outputSchema"])


def test_mcp_unsupported_protocol_version_is_protocol_error_without_db_access(
    tmp_path: Path,
):
    db_path = tmp_path / "not-created" / "mcp.sqlite3"

    with _McpProcess(db_path, tmp_path) as server:
        server.request(_request("server/discover", 1))
        response = server.request(
            _tool_call(
                "list_bills",
                2,
                protocol_version="2099-01-01",
            )
        )

    assert "error" in response
    assert "result" not in response
    assert "unsupported" in json.dumps(response).lower()
    assert not db_path.exists()


def test_mcp_unknown_tool_is_protocol_error(tmp_path: Path):
    db_path = tmp_path / "mcp.sqlite3"
    asyncio.run(_create_schema(db_path))
    before = db_path.read_bytes()

    with _McpProcess(db_path, tmp_path) as server:
        server.request(_request("server/discover", 1))
        response = server.request(_tool_call("mark_bill_paid", 2))

    assert "error" in response
    assert "result" not in response
    assert db_path.read_bytes() == before


def test_mcp_invalid_arguments_are_tool_error_without_mutation(tmp_path: Path):
    db_path = tmp_path / "mcp.sqlite3"
    asyncio.run(_create_schema(db_path))
    bill_id = asyncio.run(_seed_bill(db_path))

    with _McpProcess(db_path, tmp_path) as server:
        server.request(_request("server/discover", 1))
        result = server.request(
            _tool_call(
                "get_bill",
                2,
                {"bill_id": bill_id, "unexpected": "reject me"},
            )
        )["result"]

    assert result["resultType"] == "complete"
    assert result["isError"] is True
    assert result["structuredContent"]["code"] == "invalid_argument"
    assert asyncio.run(_bill_exists(db_path, bill_id))


def test_mcp_missing_bill_is_structured_resource_error(tmp_path: Path):
    db_path = tmp_path / "mcp.sqlite3"
    asyncio.run(_create_schema(db_path))

    with _McpProcess(db_path, tmp_path) as server:
        server.request(_request("server/discover", 1))
        result = server.request(_tool_call("get_bill", 2, {"bill_id": 9999}))["result"]

    assert result["resultType"] == "complete"
    assert result["isError"] is True
    assert result["structuredContent"]["code"] == "resource_not_found"
    assert result["structuredContent"]["message"]


def test_mcp_success_has_matching_structured_and_text_content(tmp_path: Path):
    db_path = tmp_path / "mcp.sqlite3"
    asyncio.run(_create_schema(db_path))
    bill_id = asyncio.run(_seed_bill(db_path))

    with _McpProcess(db_path, tmp_path) as server:
        server.request(_request("server/discover", 1))
        result = server.request(_tool_call("get_bill", 2, {"bill_id": bill_id}))[
            "result"
        ]

    assert result["resultType"] == "complete"
    assert result.get("isError") is not True
    structured = result["structuredContent"]
    text_blocks = [block for block in result["content"] if block["type"] == "text"]
    assert text_blocks
    assert json.loads(text_blocks[0]["text"]) == structured
    assert structured["data"]["total_amount"] == {
        "currency": "TWD",
        "value": "1234",
    }
    assert "pdf_url" not in structured["data"]
    assert "file_path" not in structured["data"]


def test_mcp_raw_protocol_errors_are_safe_before_discovery(tmp_path: Path):
    db_path = tmp_path / "mcp.sqlite3"
    asyncio.run(_create_schema(db_path))
    malformed = (
        '{"jsonrpc":"2.0","method":"server/discover","params":'
        '{"secret":"RAW_SECRET","card":"4111111111111111"}'
    )

    with _McpProcess(db_path, tmp_path) as server:
        parse_error = server.raw_line(malformed)
        assert parse_error["error"]["code"] == -32700
        assert parse_error["id"] is None
        assert "result" not in parse_error
        assert "resultType" not in parse_error

        invalid_request = server.raw_line("[]")
        assert invalid_request["error"]["code"] == -32600
        assert invalid_request["id"] is None
        assert "result" not in invalid_request

        discovery = server.request(_request("server/discover", 1))
        assert discovery["result"]["resultType"] == "complete"

    assert "RAW_SECRET" not in server.stderr_text
    assert "4111111111111111" not in server.stderr_text
