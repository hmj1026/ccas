"""Official-SDK stdio MCP adapter for the read-only Agent query surface.

The service layer owns query semantics and Agent DTOs.  This module only owns
MCP descriptors, input validation, wire envelopes, and process lifecycle.
There are deliberately no mutation handlers in this change, including when
``AGENT_WRITE_ENABLED`` is true.
"""

from __future__ import annotations

import asyncio
import contextvars
import json
import logging
from types import TracebackType
from typing import Any

import anyio
from mcp import types
from mcp.server import Server
from mcp.server.context import ServerRequestContext
from mcp.server.stdio import stdio_server
from mcp.shared._stream_protocols import ReadStream, WriteStream
from mcp.shared.exceptions import MCPError
from mcp.shared.message import SessionMessage
from pydantic import BaseModel, ValidationError

from ccas.config import get_settings
from ccas.mcp import __version__
from ccas.services.bills import get_bill, get_payment_due, list_bills
from ccas.services.budgets import budget_status
from ccas.services.identity import sanitize_text
from ccas.services.pipeline import pipeline_status
from ccas.services.schemas import (
    AgentQueryError,
    BillResult,
    BillsPage,
    BudgetStatusInput,
    BudgetStatusResult,
    EmptyInput,
    GetBillInput,
    ListBillsInput,
    PaymentDueResult,
    PipelineStatusResult,
    QueryTransactionsInput,
    ServiceProjection,
    TransactionsPage,
)
from ccas.services.transactions import query_transactions
from ccas.storage.database import get_session_factory

logger = logging.getLogger(__name__)

_PARSE_ERROR = -32700
_INVALID_REQUEST = -32600
_METHOD_NOT_FOUND = -32601
_PROTOCOL_VERSION = "2026-07-28"


class _ToolSpec:
    """Static descriptor metadata for one Agent read tool."""

    def __init__(
        self,
        name: str,
        description: str,
        input_model: type[BaseModel],
        output_model: type[BaseModel],
    ) -> None:
        self.name = name
        self.description = description
        self.input_model = input_model
        self.output_model = output_model


_TOOL_SPECS: tuple[_ToolSpec, ...] = (
    _ToolSpec(
        "list_bills",
        "List CCAS bills with optional month, year, bank, payment-status, "
        "and pagination filters.",
        ListBillsInput,
        BillsPage,
    ),
    _ToolSpec(
        "get_bill",
        "Get one CCAS bill by its database ID, including its reconciliation identity.",
        GetBillInput,
        BillResult,
    ),
    _ToolSpec(
        "query_transactions",
        "Query CCAS transactions with filters, deterministic sorting, and pagination.",
        QueryTransactionsInput,
        TransactionsPage,
    ),
    _ToolSpec(
        "get_payment_due",
        "List all unpaid CCAS bills ordered by due date.",
        EmptyInput,
        PaymentDueResult,
    ),
    _ToolSpec(
        "budget_status",
        "Read configured CCAS budgets, optionally including current-period spending.",
        BudgetStatusInput,
        BudgetStatusResult,
    ),
    _ToolSpec(
        "pipeline_status",
        "Read the most recent CCAS pipeline run and its safe human-review status.",
        EmptyInput,
        PipelineStatusResult,
    ),
)
_TOOL_BY_NAME = {spec.name: spec for spec in _TOOL_SPECS}


def _tool_descriptors() -> list[types.Tool]:
    """Build deterministic MCP descriptors from the canonical Pydantic DTOs."""
    annotations = types.ToolAnnotations(
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
    )
    return [
        types.Tool(
            name=spec.name,
            description=spec.description,
            input_schema=spec.input_model.model_json_schema(),
            output_schema=spec.output_model.model_json_schema(),
            annotations=annotations,
        )
        for spec in _TOOL_SPECS
    ]


def _text_content(payload: dict[str, Any]) -> types.TextContent:
    """Return one compact, newline-free compatibility text block."""
    return types.TextContent(
        type="text",
        text=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
    )


def _business_error_payload(error: AgentQueryError) -> dict[str, Any]:
    """Serialize only the public business-error envelope.

    ``AgentQueryError.data`` is intentionally omitted: it is an internal
    extension point and may contain resource paths or database details.
    ``sanitize_text`` is a final defense for messages supplied by a service.
    """
    payload: dict[str, Any] = {
        "code": error.code,
        "message": sanitize_text(error.message),
    }
    if error.code == "needs_human":
        payload["needs_human"] = True
    return payload


def _tool_error(error: AgentQueryError) -> types.CallToolResult:
    payload = _business_error_payload(error)
    return types.CallToolResult(
        content=[_text_content(payload)],
        structured_content=payload,
        is_error=True,
        result_type="complete",
    )


def _generic_tool_error() -> types.CallToolResult:
    """Return a safe, actionable error for unexpected service failures."""
    return _tool_error(
        AgentQueryError(
            "needs_human",
            "Agent query failed; manual review and check required.",
            needs_human=True,
        )
    )


async def _execute_tool(name: str, arguments: dict[str, Any]) -> ServiceProjection[Any]:
    """Validate one tool's arguments and dispatch through shared services."""
    spec = _TOOL_BY_NAME.get(name)
    if spec is None:
        raise MCPError(code=_METHOD_NOT_FOUND, message="Tool not found")

    try:
        input_dto = spec.input_model.model_validate(arguments, strict=True)
    except ValidationError as exc:
        raise AgentQueryError("invalid_argument", "Invalid argument provided.") from exc

    session_factory = get_session_factory()
    async with session_factory() as session:
        if name == "list_bills":
            dto = input_dto
            assert isinstance(dto, ListBillsInput)
            projection = await list_bills(session, **dto.model_dump())
        elif name == "get_bill":
            dto = input_dto
            assert isinstance(dto, GetBillInput)
            projection = await get_bill(session, bill_id=dto.bill_id)
        elif name == "query_transactions":
            dto = input_dto
            assert isinstance(dto, QueryTransactionsInput)
            projection = await query_transactions(session, **dto.model_dump())
        elif name == "get_payment_due":
            if not isinstance(input_dto, EmptyInput):  # pragma: no cover - type guard
                raise AgentQueryError("invalid_argument", "Invalid argument provided.")
            projection = await get_payment_due(session)
        elif name == "budget_status":
            dto = input_dto
            assert isinstance(dto, BudgetStatusInput)
            projection = await budget_status(session, **dto.model_dump())
        elif name == "pipeline_status":
            if not isinstance(input_dto, EmptyInput):  # pragma: no cover - type guard
                raise AgentQueryError("invalid_argument", "Invalid argument provided.")
            projection = await pipeline_status(session)
        else:  # pragma: no cover - registry and branch are intentionally exhaustive
            raise MCPError(code=_METHOD_NOT_FOUND, message="Tool not found")

    return projection


async def _on_list_tools(
    _ctx: ServerRequestContext[Any], _params: types.PaginatedRequestParams | None
) -> types.ListToolsResult:
    return types.ListToolsResult(tools=_tool_descriptors(), result_type="complete")


async def _on_discover(
    _ctx: ServerRequestContext[Any], _params: types.RequestParams
) -> types.DiscoverResult:
    """Return the modern discovery capabilities without a false listChanged flag."""
    return types.DiscoverResult(
        supported_versions=[_PROTOCOL_VERSION],
        capabilities=types.ServerCapabilities(tools=types.ToolsCapability()),
        result_type="complete",
    )


async def _on_call_tool(
    _ctx: Any, params: types.CallToolRequestParams
) -> types.CallToolResult:
    """Handle a valid MCP tools/call request with layered error mapping."""
    try:
        projection = await _execute_tool(params.name, params.arguments or {})
        if (
            params.name == "pipeline_status"
            and isinstance(projection.payload, PipelineStatusResult)
            and projection.payload.data.needs_human
        ):
            return _tool_error(
                AgentQueryError(
                    "needs_human",
                    "Pipeline execution failed after retries were exhausted; "
                    "manual review and check required.",
                    needs_human=True,
                )
            )
        payload = projection.payload.model_dump(mode="json")
        return types.CallToolResult(
            content=[_text_content(payload)],
            structured_content=payload,
            result_type="complete",
        )
    except MCPError:
        # Unknown tools are JSON-RPC protocol errors, not business failures.
        raise
    except AgentQueryError as exc:
        return _tool_error(exc)
    except Exception:
        # Never log the exception object: SQLAlchemy/Pydantic exceptions may
        # echo sensitive database values or paths to stderr.
        logger.error("MCP Agent tool failed: %s", params.name)
        return _generic_tool_error()


def _protocol_error(exc: Exception) -> SessionMessage:
    """Translate SDK parser exceptions without echoing their input payload."""
    code = _PARSE_ERROR
    if not isinstance(exc, ValidationError):
        code = _INVALID_REQUEST
    else:
        try:
            if not any(error.get("type") == "json_invalid" for error in exc.errors()):
                code = _INVALID_REQUEST
        except Exception:  # pragma: no cover - defensive against custom SDK errors
            code = _INVALID_REQUEST

    message = "Parse error" if code == _PARSE_ERROR else "Invalid Request"
    return SessionMessage(
        types.JSONRPCError(
            jsonrpc="2.0",
            id=None,
            error=types.ErrorData(code=code, message=message),
        )
    )


class _ProtocolErrorReadStream:
    """Filter SDK parser exceptions into standard JSON-RPC error messages.

    ``mcp.server.stdio`` intentionally yields parser exceptions so callers may
    choose a policy. The stock low-level runner drops those exceptions. The
    project contract requires malformed frames to receive -32700/-32600, so
    this small transport adapter emits the response and lets valid messages
    continue through the official SDK runner.
    """

    def __init__(
        self,
        inner: ReadStream[SessionMessage | Exception],
        output: WriteStream[SessionMessage],
    ) -> None:
        self._inner = inner
        self._output = output

    @property
    def last_context(self) -> contextvars.Context | None:
        return getattr(self._inner, "last_context", None)

    async def receive(self) -> SessionMessage | Exception:
        while True:
            item = await self._inner.receive()
            if isinstance(item, Exception):
                await self._output.send(_protocol_error(item))
                continue
            return item

    async def aclose(self) -> None:
        await self._inner.aclose()

    def __aiter__(self) -> _ProtocolErrorReadStream:
        return self

    async def __anext__(self) -> SessionMessage | Exception:
        try:
            return await self.receive()
        except anyio.EndOfStream:
            raise StopAsyncIteration from None

    async def __aenter__(self) -> _ProtocolErrorReadStream:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool | None:
        await self.aclose()
        return None


def create_server() -> Server[Any]:
    """Create a fresh read-only MCP server instance."""
    server = Server(
        "ccas-agent-mcp",
        version=__version__,
        description="Read-only CCAS bill, transaction, budget, and pipeline queries.",
        on_list_tools=_on_list_tools,
        on_call_tool=_on_call_tool,
    )
    # The SDK's default modern capability derivation serializes
    # ``listChanged=false``.  This server does not implement change
    # notifications, so omit the hint entirely as required by the contract.
    server.add_request_handler("server/discover", types.RequestParams, _on_discover)
    return server


async def run_server() -> None:
    """Run one stdio connection and close all transport resources on EOF."""
    # Resolve settings before entering stdio so configuration errors do not
    # print a traceback to the MCP stdout stream. The read-only server does
    # not use the write gate, but Settings remains the configuration SSOT.
    get_settings()
    server = create_server()
    async with stdio_server() as (read_stream, write_stream):
        filtered_read_stream = _ProtocolErrorReadStream(read_stream, write_stream)
        await server.run(
            filtered_read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def main() -> None:
    """Console entry point for ``ccas-mcp``."""
    asyncio.run(run_server())


__all__ = ["create_server", "main", "run_server"]
