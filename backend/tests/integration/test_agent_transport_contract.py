"""Cross-transport contracts for the read-only Agent MCP and CLI surfaces."""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

import jsonschema
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ccas.storage.models import (
    BankConfig,
    BankLoginCredential,
    BankSecret,
    Bill,
    Budget,
    GmailOAuthState,
    PipelineRun,
    PipelineRunStatus,
    PipelineRunTerminalReason,
    Transaction,
)
from tests.integration import test_agent_cli as cli_wire
from tests.integration import test_agent_mcp as mcp_wire

_READ_COMMANDS: tuple[tuple[str, list[str]], ...] = (
    ("list_bills", ["list-bills"]),
    ("get_bill", ["get-bill"]),
    ("query_transactions", ["query-transactions"]),
    ("get_payment_due", ["get-payment-due"]),
    ("budget_status", ["budget-status"]),
    ("pipeline_status", ["pipeline-status"]),
)

PDF_PASSWORD_SENTINEL = "pdf-password-sentinel-7f3c"
OAUTH_TOKEN_SENTINEL = "oauth-refresh-sentinel-9a2d"
SESSION_SECRET_SENTINEL = "session-secret-sentinel-4b8e"
FULL_PAN_SENTINEL = "4111111111111111"
PRIVATE_PATH_SENTINEL = "/srv/ccas/private/statement.pdf"
PRIVATE_DB_PATH_SENTINEL = "/srv/ccas/private/ccas.sqlite3"
_SENSITIVE_VALUES = (
    PDF_PASSWORD_SENTINEL,
    OAUTH_TOKEN_SENTINEL,
    SESSION_SECRET_SENTINEL,
    FULL_PAN_SENTINEL,
    PRIVATE_PATH_SENTINEL,
    PRIVATE_DB_PATH_SENTINEL,
)
_RAW_ERROR_MARKERS = ("Traceback", "sqlalchemy.exc", "sqlite+aiosqlite://")


async def _seed_transport_fixture(db_path: Path) -> int:
    """建立六個唯讀查詢都能成功讀取的資料集，並埋入不可輸出的私密值。"""
    engine = create_async_engine(cli_wire._database_url(db_path))
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        session.add(
            BankConfig(
                bank_code="CTBC",
                bank_name="中國信託",
                gmail_filter=f"from:billing {OAUTH_TOKEN_SENTINEL}",
                pdf_password_rule=PDF_PASSWORD_SENTINEL,
            )
        )
        session.add_all(
            [
                BankSecret(
                    bank_code="CTBC",
                    encrypted_password=PDF_PASSWORD_SENTINEL,
                ),
                BankLoginCredential(
                    bank_code="CTBC",
                    credential_key="NATIONAL_ID",
                    encrypted_value=OAUTH_TOKEN_SENTINEL,
                ),
                GmailOAuthState(
                    state="oauth-state-sentinel",
                    code_verifier=SESSION_SECRET_SENTINEL,
                ),
            ]
        )
        bill = Bill(
            bank_code="CTBC",
            billing_month="2026-03",
            total_amount=1234,
            due_date=date(2026, 4, 15),
            is_paid=False,
            file_path=PRIVATE_PATH_SENTINEL,
        )
        session.add(bill)
        await session.flush()
        session.add(
            Transaction(
                bill_id=bill.id,
                trans_date=date(2026, 3, 2),
                posting_date=date(2026, 3, 3),
                merchant="Safe merchant",
                amount=-123,
                currency="TWD",
                original_amount=-123,
                card_last4="4242",
                category="food",
                note=FULL_PAN_SENTINEL,
            )
        )
        session.add(
            Budget(
                scope="monthly_total",
                scope_ref=None,
                amount_ntd=10000,
                alert_threshold_percent=80,
                enabled=True,
            )
        )
        run = PipelineRun(
            id="run-success",
            job_id="job-success",
            status=PipelineRunStatus.SUCCEEDED,
            triggered_by="api",
            params={
                "force": False,
                "password": PDF_PASSWORD_SENTINEL,
                "oauth_token": OAUTH_TOKEN_SENTINEL,
                "session_secret": SESSION_SECRET_SENTINEL,
                "file_path": PRIVATE_DB_PATH_SENTINEL,
            },
            current_stage="parse",
            current_stage_processed=1,
            current_stage_total=1,
            stage_summary=[
                {
                    "stage": "parse",
                    "ok": 1,
                    "fail": 0,
                    "elapsed_ms": 8,
                    "counts": {"parsed": 1},
                    "errors": [
                        "internal detail: "
                        f"{PDF_PASSWORD_SENTINEL} {PRIVATE_PATH_SENTINEL}"
                    ],
                }
            ],
            error_message=(
                f"internal detail: {FULL_PAN_SENTINEL} {OAUTH_TOKEN_SENTINEL}"
            ),
            created_at=datetime(2026, 4, 1, 12, 0, 0),
        )
        run.terminal_reason = PipelineRunTerminalReason.SUCCEEDED
        session.add(run)
        await session.commit()
        bill_id = bill.id
    await engine.dispose()
    return bill_id


async def _add_needs_human_run(db_path: Path) -> None:
    """在成功 fixture 後加入一筆含污染內容的重試耗盡執行紀錄。"""
    engine = create_async_engine(cli_wire._database_url(db_path))
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        run = PipelineRun(
            id="run-needs-human",
            job_id="job-needs-human",
            status=PipelineRunStatus.FAILED,
            triggered_by="api",
            params={"file_path": PRIVATE_DB_PATH_SENTINEL},
            current_stage="parse",
            current_stage_processed=0,
            current_stage_total=1,
            stage_summary=[
                {
                    "stage": "parse",
                    "ok": 0,
                    "fail": 1,
                    "elapsed_ms": 4,
                    "counts": {},
                    "errors": [OAUTH_TOKEN_SENTINEL],
                }
            ],
            error_message=f"failure: {PDF_PASSWORD_SENTINEL} {FULL_PAN_SENTINEL}",
            created_at=datetime(2026, 4, 2, 12, 0, 0),
        )
        run.terminal_reason = PipelineRunTerminalReason.RETRIES_EXHAUSTED
        session.add(run)
        await session.commit()
    await engine.dispose()


def _assert_no_sensitive_values(text: str) -> None:
    for sentinel in _SENSITIVE_VALUES:
        assert sentinel not in text
    for marker in _RAW_ERROR_MARKERS:
        assert marker not in text


def _mcp_stderr(server: Any) -> str:
    return server.stderr_text


def _mcp_success_payload(
    result: dict[str, Any], output_schema: dict[str, Any]
) -> dict[str, Any]:
    assert result["resultType"] == "complete"
    assert result.get("isError") is not True
    structured = result["structuredContent"]
    jsonschema.Draft202012Validator(output_schema).validate(structured)
    text_blocks = [block for block in result["content"] if block["type"] == "text"]
    assert text_blocks
    assert json.loads(text_blocks[0]["text"]) == structured
    return structured


def _mcp_call_arguments(tool_name: str, bill_id: int) -> dict[str, Any]:
    if tool_name == "get_bill":
        return {"bill_id": bill_id}
    return {}


def test_mcp_and_cli_success_payloads_match_for_all_six_reads(
    tmp_path: Path,
):
    """六個唯讀工具的 MCP structured/text 與 CLI JSON 必須完全一致。"""
    db_path = tmp_path / "transport.sqlite3"
    asyncio.run(mcp_wire._create_schema(db_path))
    bill_id = asyncio.run(_seed_transport_fixture(db_path))

    mcp_payloads: dict[str, dict[str, Any]] = {}
    with mcp_wire._McpProcess(db_path, tmp_path) as server:
        discovery = server.request(mcp_wire._request("server/discover", 1))
        assert discovery["result"]["resultType"] == "complete"
        listed = server.request(mcp_wire._request("tools/list", 2))["result"]
        assert listed["resultType"] == "complete"
        definitions = {tool["name"]: tool for tool in listed["tools"]}
        assert tuple(definitions) == mcp_wire._READ_TOOLS
        for definition in definitions.values():
            jsonschema.Draft202012Validator.check_schema(definition["inputSchema"])
            jsonschema.Draft202012Validator.check_schema(definition["outputSchema"])

        for request_id, (tool_name, _command) in enumerate(_READ_COMMANDS, start=3):
            result = server.request(
                mcp_wire._tool_call(
                    tool_name,
                    request_id,
                    _mcp_call_arguments(tool_name, bill_id),
                )
            )["result"]
            mcp_payloads[tool_name] = _mcp_success_payload(
                result, definitions[tool_name]["outputSchema"]
            )
            _assert_no_sensitive_values(json.dumps(result))

    mcp_diagnostics = _mcp_stderr(server)
    _assert_no_sensitive_values(mcp_diagnostics)

    for tool_name, command in _READ_COMMANDS:
        args = list(command)
        if tool_name == "get_bill":
            args.extend(["--bill-id", str(bill_id)])
        result = cli_wire._run_cli(db_path, tmp_path, args)
        assert result.returncode == 0, result.stderr
        _assert_no_sensitive_values(result.stdout + result.stderr)
        assert json.loads(result.stdout) == mcp_payloads[tool_name]


def test_invalid_extra_arguments_are_safe_for_all_six_cli_and_mcp_reads(
    tmp_path: Path,
):
    """未知欄位一律是業務輸入錯誤，且不回顯帶入的敏感值。"""
    db_path = tmp_path / "invalid.sqlite3"
    asyncio.run(mcp_wire._create_schema(db_path))
    bill_id = asyncio.run(_seed_transport_fixture(db_path))
    invalid_sentinel = f"unexpected-{FULL_PAN_SENTINEL}-{OAUTH_TOKEN_SENTINEL}"

    with mcp_wire._McpProcess(db_path, tmp_path) as server:
        server.request(mcp_wire._request("server/discover", 1))
        for request_id, (tool_name, _command) in enumerate(_READ_COMMANDS, start=2):
            arguments = _mcp_call_arguments(tool_name, bill_id)
            arguments["unexpected"] = invalid_sentinel
            result = server.request(
                mcp_wire._tool_call(tool_name, request_id, arguments)
            )["result"]
            assert result["resultType"] == "complete"
            assert result["isError"] is True
            assert result["structuredContent"]["code"] == "invalid_argument"
            assert "needs_human" not in result["structuredContent"]
            _assert_no_sensitive_values(json.dumps(result))

    mcp_diagnostics = _mcp_stderr(server)
    _assert_no_sensitive_values(mcp_diagnostics)

    for tool_name, command in _READ_COMMANDS:
        args = list(command)
        if tool_name == "get_bill":
            args.extend(["--bill-id", str(bill_id)])
        args.extend(["--unexpected", invalid_sentinel])
        result = cli_wire._run_cli(db_path, tmp_path, args)
        assert result.returncode != 0
        _assert_no_sensitive_values(result.stdout + result.stderr)


def test_needs_human_errors_are_actionable_without_private_details(tmp_path: Path):
    """重試耗盡的 pipeline 錯誤可辨識，但不帶出污染資料。"""
    db_path = tmp_path / "needs-human.sqlite3"
    asyncio.run(mcp_wire._create_schema(db_path))
    asyncio.run(_seed_transport_fixture(db_path))
    asyncio.run(_add_needs_human_run(db_path))

    with mcp_wire._McpProcess(db_path, tmp_path) as server:
        server.request(mcp_wire._request("server/discover", 1))
        result = server.request(mcp_wire._tool_call("pipeline_status", 2, {}))["result"]

    mcp_diagnostics = _mcp_stderr(server)
    assert result["resultType"] == "complete"
    assert result["isError"] is True
    error = result["structuredContent"]
    assert error["code"] == "needs_human"
    assert error["needs_human"] is True
    assert error["message"]
    _assert_no_sensitive_values(json.dumps(result) + mcp_diagnostics)

    cli_result = cli_wire._run_cli(db_path, tmp_path, ["pipeline-status"])
    assert cli_result.returncode != 0
    cli_output = cli_result.stdout + cli_result.stderr
    assert "needs_human" in cli_output
    _assert_no_sensitive_values(cli_output)


@pytest.mark.parametrize("write_enabled", [False, True])
def test_mcp_write_flag_still_exposes_only_reads_and_rejects_direct_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    write_enabled: bool,
):
    """AGENT_WRITE_ENABLED 不會曝光寫入工具或允許未授權 mutation。"""
    db_path = tmp_path / f"write-flag-{write_enabled}.sqlite3"
    asyncio.run(mcp_wire._create_schema(db_path))
    before = db_path.read_bytes()
    original_environment = mcp_wire._test_environment

    def _environment_with_flag(
        database_path: Path,
        test_tmp_path: Path,
        *,
        _write_enabled: bool = write_enabled,
    ) -> dict[str, str]:
        environment = original_environment(database_path, test_tmp_path)
        environment["AGENT_WRITE_ENABLED"] = str(_write_enabled).lower()
        return environment

    monkeypatch.setattr(mcp_wire, "_test_environment", _environment_with_flag)
    with mcp_wire._McpProcess(db_path, tmp_path) as server:
        server.request(mcp_wire._request("server/discover", 1))
        listed = server.request(mcp_wire._request("tools/list", 2))["result"]
        assert [tool["name"] for tool in listed["tools"]] == list(mcp_wire._READ_TOOLS)
        write_response = server.request(
            mcp_wire._tool_call("mark_bill_paid", 3, {"bill_id": 1})
        )

    diagnostics = _mcp_stderr(server)
    assert "error" in write_response
    assert "result" not in write_response
    assert db_path.read_bytes() == before
    _assert_no_sensitive_values(diagnostics)


def test_mcp_unknown_method_is_protocol_error_without_db_mutation(tmp_path: Path):
    """未知 JSON-RPC method 使用 protocol error，且不觸碰資料庫。"""
    db_path = tmp_path / "unknown-method.sqlite3"
    asyncio.run(mcp_wire._create_schema(db_path))
    before = db_path.read_bytes()

    with mcp_wire._McpProcess(db_path, tmp_path) as server:
        response = server.request(mcp_wire._request("unknown/method", 1))

    assert "error" in response
    assert response["error"]["code"] == -32601
    assert "result" not in response
    assert db_path.read_bytes() == before
    _assert_no_sensitive_values(server.stderr_text)


def test_official_mcp_sdk_can_discover_list_and_call_same_host_server(
    tmp_path: Path,
):
    """官方 mcp 2.x client 可完成 discovery、tools/list 與一次讀取。"""
    db_path = tmp_path / "sdk.sqlite3"
    asyncio.run(mcp_wire._create_schema(db_path))
    bill_id = asyncio.run(_seed_transport_fixture(db_path))

    async def _round_trip() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        from mcp import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client

        server_parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "ccas.mcp"],
            env=mcp_wire._test_environment(db_path, tmp_path),
            cwd=str(mcp_wire._BACKEND_ROOT),
        )
        async with stdio_client(server_parameters) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                discovery = await session.discover()
                listed = await session.list_tools()
                call = await session.call_tool("get_bill", {"bill_id": bill_id})
        return (
            discovery.model_dump(by_alias=True, mode="json"),
            listed.model_dump(by_alias=True, mode="json"),
            call.model_dump(by_alias=True, mode="json"),
        )

    discovery, listed, call = asyncio.run(_round_trip())
    assert discovery["resultType"] == "complete"
    assert discovery["_meta"]["io.modelcontextprotocol/serverInfo"]["name"]
    assert [tool["name"] for tool in listed["tools"]] == list(mcp_wire._READ_TOOLS)
    assert call["resultType"] == "complete"
    assert call["structuredContent"]["data"]["id"] == bill_id
    _assert_no_sensitive_values(
        json.dumps(discovery) + json.dumps(listed) + json.dumps(call)
    )
