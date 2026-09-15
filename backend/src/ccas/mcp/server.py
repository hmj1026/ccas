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
import re
from collections.abc import Awaitable, Callable, Mapping
from functools import cache
from types import TracebackType
from typing import Any

import anyio
from mcp import types
from mcp.server import Server
from mcp.server.caching import CacheableMethod, CacheHint
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
from ccas.storage.agent_queries import completion_candidates_query
from ccas.storage.database import get_session_factory

logger = logging.getLogger(__name__)

_PARSE_ERROR = -32700
_INVALID_REQUEST = -32600
_METHOD_NOT_FOUND = -32601
_INVALID_PARAMS = -32602
_INTERNAL_ERROR = -32603
_PROTOCOL_VERSION = "2026-07-28"
# SEP-2549 freshness hints. The descriptor lists are derived from module-level
# constants, so they only ever change across a deploy; five minutes bounds how
# long a client may keep serving a retired descriptor.
# ``private`` because both answers are produced behind Bearer authorization.
_STATIC_LIST_TTL_MS = 300_000
_CACHE_HINTS: Mapping[CacheableMethod, CacheHint] = {
    "tools/list": CacheHint(ttl_ms=_STATIC_LIST_TTL_MS, scope="private"),
    "server/discover": CacheHint(ttl_ms=_STATIC_LIST_TTL_MS, scope="private"),
    "prompts/list": CacheHint(ttl_ms=_STATIC_LIST_TTL_MS, scope="private"),
    "resources/list": CacheHint(ttl_ms=_STATIC_LIST_TTL_MS, scope="private"),
    "resources/templates/list": CacheHint(ttl_ms=_STATIC_LIST_TTL_MS, scope="private"),
    # `resources/read` is intentionally absent: its payload is live CCAS data.
}


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

_JSON_MIME_TYPE = "application/json"
_PIPELINE_STATUS_URI = "ccas://pipeline/status"
_PAYMENT_DUE_URI = "ccas://payment-due"
_BILL_URI_TEMPLATE = "ccas://bill/{bill_id}"
# Derived so the advertised template and the matcher cannot drift apart: a URI
# shape edited in one but not the other would advertise a template that never
# resolves, and nothing would catch it.
_BILL_URI_PATTERN = re.compile(
    "^"
    + re.escape(_BILL_URI_TEMPLATE).replace(r"\{bill_id\}", r"(?P<bill_id>\d+)")
    + "$"
)
_PROMPT_RECONCILE = "reconcile_with_notion"
_PROMPT_BUDGET_REVIEW = "monthly_budget_review"
_MONTH_ARGUMENT = "month"
_BILL_ID_ARGUMENT = "bill_id"
# Completions are suggestions, not an index. One service page bounds the work;
# ``has_more`` tells the client the list is truncated rather than exhaustive.
_COMPLETION_PAGE_SIZE = 100


@cache
def _tool_descriptor_cache() -> tuple[types.Tool, ...]:
    """Build the descriptors once; `model_json_schema()` dominates this call.

    Measured at ~11 ms per build (two schema generations per tool), against
    ~2 µs for the resource and prompt descriptor lists, which is why only this
    one is memoized. The inputs are module constants, so the result is fixed for
    the process lifetime — the same assumption the `tools/list` cache hint
    already encodes.
    """
    annotations = types.ToolAnnotations(
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
    )
    return tuple(
        types.Tool(
            name=spec.name,
            description=spec.description,
            input_schema=spec.input_model.model_json_schema(),
            output_schema=spec.output_model.model_json_schema(),
            annotations=annotations,
        )
        for spec in _TOOL_SPECS
    )


def _tool_descriptors() -> list[types.Tool]:
    """Return a fresh list over the shared, immutable-by-convention descriptors."""
    return list(_tool_descriptor_cache())


def _compact_json(payload: dict[str, Any]) -> str:
    """Encode one payload in this server's wire format.

    Single source for the compact, newline-free encoding: tool results and
    resource contents must not drift apart on separators or escaping.
    """
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _text_content(payload: dict[str, Any]) -> types.TextContent:
    """Return one compact, newline-free compatibility text block."""
    return types.TextContent(type="text", text=_compact_json(payload))


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
        capabilities=types.ServerCapabilities(
            tools=types.ToolsCapability(),
            resources=types.ResourcesCapability(),
            prompts=types.PromptsCapability(),
            completions=types.CompletionsCapability(),
        ),
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


# --- Resources -------------------------------------------------------------


def _resource_descriptors() -> list[types.Resource]:
    """The two fixed projections a host can attach as context."""
    return [
        types.Resource(
            name="pipeline_status",
            title="CCAS pipeline status",
            uri=_PIPELINE_STATUS_URI,
            description=(
                "The most recent CCAS pipeline run and its safe human-review status."
            ),
            mime_type=_JSON_MIME_TYPE,
        ),
        types.Resource(
            name="payment_due",
            title="CCAS unpaid bills",
            uri=_PAYMENT_DUE_URI,
            description="All unpaid CCAS bills ordered by due date.",
            mime_type=_JSON_MIME_TYPE,
        ),
    ]


def _resource_template_descriptors() -> list[types.ResourceTemplate]:
    return [
        types.ResourceTemplate(
            name="bill",
            title="CCAS bill",
            uri_template=_BILL_URI_TEMPLATE,
            description=(
                "One CCAS bill by database ID, including its reconciliation identity."
            ),
            mime_type=_JSON_MIME_TYPE,
        )
    ]


async def _read_projection(uri: str) -> ServiceProjection[Any]:
    """Resolve one resource URI through the shared read-only services."""
    match = _BILL_URI_PATTERN.match(uri)
    if match is None and uri not in (_PIPELINE_STATUS_URI, _PAYMENT_DUE_URI):
        raise MCPError(code=_INVALID_PARAMS, message="Resource not found")

    session_factory = get_session_factory()
    async with session_factory() as session:
        if uri == _PIPELINE_STATUS_URI:
            return await pipeline_status(session)
        if uri == _PAYMENT_DUE_URI:
            return await get_payment_due(session)
        assert match is not None  # guarded above
        return await get_bill(session, bill_id=int(match["bill_id"]))


async def _on_list_resources(
    _ctx: ServerRequestContext[Any], _params: types.PaginatedRequestParams | None
) -> types.ListResourcesResult:
    return types.ListResourcesResult(
        resources=_resource_descriptors(), result_type="complete"
    )


async def _on_list_resource_templates(
    _ctx: ServerRequestContext[Any], _params: types.PaginatedRequestParams | None
) -> types.ListResourceTemplatesResult:
    return types.ListResourceTemplatesResult(
        resource_templates=_resource_template_descriptors(), result_type="complete"
    )


async def _on_read_resource(
    _ctx: Any, params: types.ReadResourceRequestParams
) -> types.ReadResourceResult:
    """Read one resource, mapping business failures to JSON-RPC errors.

    ``ReadResourceResult`` has no error channel of its own (unlike
    ``CallToolResult.is_error``), so a business failure has to surface as a
    protocol error. The message still goes through ``_business_error_payload``
    so the same sanitization applies as on the tool path.
    """
    uri = str(params.uri)
    try:
        projection = await _read_projection(uri)
    except MCPError:
        raise
    except AgentQueryError as exc:
        # Carry the same public envelope the tool path returns, so a host can
        # still tell `needs_human` apart from a plain not-found.
        payload = _business_error_payload(exc)
        raise MCPError(
            code=_INVALID_PARAMS, message=payload["message"], data=payload
        ) from exc
    except Exception as exc:
        # Never log or forward the exception object: the SDK's JSON-RPC
        # dispatcher puts `str(exc)` straight on the wire for an uncaught
        # handler exception, and a SQLAlchemy error can carry SQL, bound
        # parameters, or the engine URL. A bad URI is the client's fault
        # (-32602); this is the server's (-32603).
        logger.error("MCP Agent resource read failed: %s", uri)
        raise MCPError(
            code=_INTERNAL_ERROR,
            message="Agent query failed; manual review and check required.",
        ) from exc

    return types.ReadResourceResult(
        contents=[
            types.TextResourceContents(
                uri=uri,
                mime_type=_JSON_MIME_TYPE,
                text=_compact_json(projection.payload.model_dump(mode="json")),
            )
        ],
        result_type="complete",
    )


# --- Prompts ---------------------------------------------------------------

# ADR-0001: Notion holds decision authority; CCAS is a verification source and
# is never written back to. Every prompt restates that so an Agent acting on
# these templates cannot drift from the recorded trust boundary.
_BOUNDARY = (
    "CCAS is a read-only verification source. Notion holds decision authority: "
    "report differences for a human to resolve, and never write CCAS values "
    "back into Notion or Notion values back into CCAS."
)


class _PromptSpec:
    """Static descriptor metadata for one Agent prompt template."""

    def __init__(self, name: str, summary: str, body: str) -> None:
        self.name = name
        self.summary = summary
        self.body = body


_PROMPT_SPECS: tuple[_PromptSpec, ...] = (
    _PromptSpec(
        _PROMPT_RECONCILE,
        "Reconcile CCAS bills and transactions against Notion for one month.",
        "Reconcile the CCAS record for {month} against Notion.\n\n"
        "1. Call list_bills and query_transactions for {month}.\n"
        "2. Compare each bill's amount, due date, and payment status with Notion.\n"
        "3. Produce a difference report: matched, CCAS-only, Notion-only, "
        "and conflicting rows.\n\n" + _BOUNDARY,
    ),
    _PromptSpec(
        _PROMPT_BUDGET_REVIEW,
        "Review configured CCAS budgets against actual spending for one month.",
        "Review CCAS budgets for {month}.\n\n"
        "1. Call budget_status with include_current_period set to true.\n"
        "2. Call query_transactions for {month} to explain the largest "
        "contributors to each over-budget scope.\n"
        "3. Summarize which budgets are on track, at risk, and exceeded.\n\n"
        + _BOUNDARY,
    ),
)
_PROMPT_BY_NAME = {spec.name: spec for spec in _PROMPT_SPECS}


def _prompt_descriptors() -> list[types.Prompt]:
    return [
        types.Prompt(
            name=spec.name,
            description=spec.summary,
            arguments=[
                types.PromptArgument(
                    name=_MONTH_ARGUMENT,
                    description="Billing month in YYYY-MM form.",
                    required=True,
                )
            ],
        )
        for spec in _PROMPT_SPECS
    ]


async def _on_list_prompts(
    _ctx: ServerRequestContext[Any], _params: types.PaginatedRequestParams | None
) -> types.ListPromptsResult:
    return types.ListPromptsResult(
        prompts=_prompt_descriptors(), result_type="complete"
    )


async def _on_get_prompt(
    _ctx: Any, params: types.GetPromptRequestParams
) -> types.GetPromptResult:
    spec = _PROMPT_BY_NAME.get(params.name)
    if spec is None:
        raise MCPError(code=_INVALID_PARAMS, message="Prompt not found")

    arguments = params.arguments or {}
    month = arguments.get(_MONTH_ARGUMENT)
    if not month:
        raise MCPError(code=_INVALID_PARAMS, message="Argument 'month' is required")
    # Arguments are host-supplied free text that ends up inside model-facing
    # instructions; sanitize before interpolation like every other echo path.
    safe_month = sanitize_text(str(month))

    return types.GetPromptResult(
        description=spec.summary,
        messages=[
            types.PromptMessage(
                role="user",
                content=types.TextContent(
                    type="text", text=spec.body.format(month=safe_month)
                ),
            )
        ],
        result_type="complete",
    )


# --- Completions -----------------------------------------------------------


async def _completion_candidates() -> tuple[list[tuple[int, str]], bool]:
    """`(bill_id, billing_month)` pairs for completion, plus a truncation flag.

    Deliberately not ``list_bills``: that resolves bank names and card last-4s
    and builds full ``AgentBill`` DTOs, all of which completion discards to keep
    two scalars.
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        return await completion_candidates_query(session, limit=_COMPLETION_PAGE_SIZE)


def _no_completions() -> types.CompleteResult:
    return types.CompleteResult(
        completion=types.Completion(values=[]), result_type="complete"
    )


def _matching(values: list[str], prefix: str) -> list[str]:
    return [value for value in values if value.startswith(prefix)]


async def _on_completion(
    _ctx: Any, params: types.CompleteRequestParams
) -> types.CompleteResult:
    """Suggest argument values for prompts and the bill resource template.

    The protocol only allows prompt and resource-template references here —
    there is no tool reference — so tool arguments cannot be completed.
    """
    argument = params.argument
    if (
        isinstance(params.ref, types.ResourceTemplateReference)
        and params.ref.uri == _BILL_URI_TEMPLATE
    ):
        completable = _BILL_ID_ARGUMENT
    elif (
        isinstance(params.ref, types.PromptReference)
        and params.ref.name in _PROMPT_BY_NAME
    ):
        completable = _MONTH_ARGUMENT
    else:
        return _no_completions()
    if argument.name != completable:
        return _no_completions()

    try:
        candidates, has_more = await _completion_candidates()
    except AgentQueryError:
        # A business failure means "no suggestions", not a protocol error.
        logger.warning("MCP Agent completion unavailable: %s", argument.name)
        return _no_completions()
    except Exception:
        # Completion is a suggestion API, so degrading to an empty list is the
        # right failure mode — but it is logged, never silent. The registration
        # guard would also catch this; keeping it here preserves the argument
        # name in the log and the empty-list shape instead of a protocol error.
        logger.error("MCP Agent completion lookup failed: %s", argument.name)
        return _no_completions()

    if completable == _BILL_ID_ARGUMENT:
        values = _matching(
            [str(bill_id) for bill_id, _month in candidates], argument.value
        )
    else:
        months: list[str] = []
        for _bill_id, month in candidates:
            if month and month not in months:
                months.append(month)
        values = _matching(months, argument.value)

    return types.CompleteResult(
        completion=types.Completion(
            values=values, total=len(values), has_more=has_more
        ),
        result_type="complete",
    )


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


def _guarded[P, R](
    method: str, handler: Callable[[Any, P], Awaitable[R]]
) -> Callable[[Any, P], Awaitable[R]]:
    """Last-resort redaction applied to every handler at registration.

    The SDK's JSON-RPC dispatcher answers an uncaught handler exception with
    `str(exc)` verbatim, so a SQLAlchemy failure would put SQL, bound parameters
    or the engine URL on the wire. Each handler already redacts its own
    failures in the shape its result type allows; this wrapper exists so a
    handler that forgets — or one added later — still cannot leak. It never
    masks an `MCPError`, which is a deliberate, already-safe protocol answer.
    """

    async def _run(ctx: Any, params: P) -> R:
        try:
            return await handler(ctx, params)
        except MCPError:
            raise
        except Exception as exc:
            logger.error("MCP Agent handler failed: %s", method)
            raise MCPError(
                code=_INTERNAL_ERROR,
                message="Agent request failed; manual review and check required.",
            ) from exc

    return _run


def create_server() -> Server[Any]:
    """Create a fresh read-only MCP server instance."""
    server = Server(
        "ccas-agent-mcp",
        version=__version__,
        description="Read-only CCAS bill, transaction, budget, and pipeline queries.",
        on_list_tools=_guarded("tools/list", _on_list_tools),
        on_call_tool=_guarded("tools/call", _on_call_tool),
        on_list_resources=_guarded("resources/list", _on_list_resources),
        on_list_resource_templates=_guarded(
            "resources/templates/list", _on_list_resource_templates
        ),
        on_read_resource=_guarded("resources/read", _on_read_resource),
        on_list_prompts=_guarded("prompts/list", _on_list_prompts),
        on_get_prompt=_guarded("prompts/get", _on_get_prompt),
        on_completion=_guarded("completion/complete", _on_completion),
        cache_hints=_CACHE_HINTS,
    )
    # The SDK's default modern capability derivation serializes
    # ``listChanged=false``.  This server does not implement change
    # notifications, so omit the hint entirely as required by the contract.
    server.add_request_handler(
        "server/discover",
        types.RequestParams,
        _guarded("server/discover", _on_discover),
    )
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
