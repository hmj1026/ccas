"""Contract tests for the MCP resources, prompts, and completion surfaces.

These drive the handlers registered by ``create_server()`` directly, against a
temp-file SQLite database, because the MCP server resolves its own session
factory (``get_session_factory``) rather than taking one by injection.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from mcp import types
from mcp.shared.exceptions import MCPError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ccas.storage.models import Base, Bill

_PIPELINE_STATUS_URI = "ccas://pipeline/status"
_PAYMENT_DUE_URI = "ccas://payment-due"
_BILL_URI_TEMPLATE = "ccas://bill/{bill_id}"
_JSON_MIME_TYPE = "application/json"
_INVALID_PARAMS = -32602
_INTERNAL_ERROR = -32603
_BILLING_MONTH = "2026-03"


@pytest.fixture
async def seeded_bill_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[int]:
    """Seed one bill and point the MCP server's session factory at it."""
    db_path = tmp_path / "mcp-resources.sqlite"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        bill = Bill(
            bank_code="CTBC",
            billing_month=_BILLING_MONTH,
            total_amount=1234,
            due_date=date(2026, 4, 15),
            is_paid=False,
        )
        session.add(bill)
        await session.commit()
        bill_id = bill.id

    import ccas.mcp.server as mcp_server

    monkeypatch.setattr(mcp_server, "get_session_factory", lambda: factory)
    yield bill_id
    await engine.dispose()


async def _call(method: str, params: Any) -> Any:
    """Invoke one registered handler through the SDK's public registry accessor."""
    from ccas.mcp.server import create_server

    entry = create_server().get_request_handler(method)
    assert entry is not None, f"{method} is not registered"
    return await entry.handler(None, params)  # pyright: ignore[reportArgumentType]


async def test_list_resources_exposes_the_two_fixed_projections() -> None:
    result = await _call("resources/list", None)

    uris = [str(resource.uri) for resource in result.resources]
    assert uris == [_PIPELINE_STATUS_URI, _PAYMENT_DUE_URI]
    assert all(r.mime_type == _JSON_MIME_TYPE for r in result.resources)


async def test_list_resource_templates_exposes_the_bill_template() -> None:
    result = await _call("resources/templates/list", None)

    templates = [t.uri_template for t in result.resource_templates]
    assert templates == [_BILL_URI_TEMPLATE]


async def test_read_resource_returns_bill_json(seeded_bill_id: int) -> None:
    params = types.ReadResourceRequestParams(uri=f"ccas://bill/{seeded_bill_id}")

    result = await _call("resources/read", params)

    assert len(result.contents) == 1
    content = result.contents[0]
    assert content.mime_type == _JSON_MIME_TYPE
    payload = json.loads(content.text)
    assert payload["data"]["id"] == seeded_bill_id
    assert payload["data"]["bank_code"] == "CTBC"


async def test_read_resource_returns_payment_due_json(seeded_bill_id: int) -> None:
    params = types.ReadResourceRequestParams(uri=_PAYMENT_DUE_URI)

    result = await _call("resources/read", params)

    payload = json.loads(result.contents[0].text)
    assert [bill["id"] for bill in payload["data"]] == [seeded_bill_id]


async def test_read_resource_rejects_unknown_uri(seeded_bill_id: int) -> None:
    params = types.ReadResourceRequestParams(uri="ccas://nope")

    with pytest.raises(MCPError) as exc_info:
        await _call("resources/read", params)

    assert exc_info.value.error.code == _INVALID_PARAMS


async def test_read_resource_internal_failure_never_echoes_the_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The SDK dispatcher puts `str(exc)` on the wire; nothing may reach it."""
    import ccas.mcp.server as mcp_server

    secret = "SELECT * FROM bills WHERE token='super-secret'"

    async def _boom(_uri: str) -> Any:
        raise RuntimeError(secret)

    monkeypatch.setattr(mcp_server, "_read_projection", _boom)
    params = types.ReadResourceRequestParams(uri=_PIPELINE_STATUS_URI)

    with pytest.raises(MCPError) as exc_info:
        await _call("resources/read", params)

    assert exc_info.value.error.code == _INTERNAL_ERROR
    assert secret not in exc_info.value.error.message


async def test_completion_internal_failure_degrades_to_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unexpected failure must not propagate raw exception text to the wire."""
    import ccas.mcp.server as mcp_server

    async def _boom() -> Any:
        raise RuntimeError("SELECT * FROM bills WHERE token='super-secret'")

    monkeypatch.setattr(mcp_server, "_completion_candidates", _boom)
    params = types.CompleteRequestParams(
        ref=types.PromptReference(type="ref/prompt", name="reconcile_with_notion"),
        argument=types.CompletionArgument(name="month", value=""),
    )

    result = await _call("completion/complete", params)

    assert result.completion.values == []


async def test_read_resource_missing_bill_carries_the_business_envelope(
    seeded_bill_id: int,
) -> None:
    params = types.ReadResourceRequestParams(uri=f"ccas://bill/{seeded_bill_id + 999}")

    with pytest.raises(MCPError) as exc_info:
        await _call("resources/read", params)

    assert exc_info.value.error.code == _INVALID_PARAMS
    assert "Traceback" not in exc_info.value.error.message
    assert exc_info.value.error.data["code"] == "resource_not_found"


async def test_list_prompts_exposes_both_reconciliation_prompts() -> None:
    result = await _call("prompts/list", None)

    names = [prompt.name for prompt in result.prompts]
    assert names == ["reconcile_with_notion", "monthly_budget_review"]


async def test_get_prompt_carries_the_notion_authority_boundary() -> None:
    params = types.GetPromptRequestParams(
        name="reconcile_with_notion",
        arguments={"month": _BILLING_MONTH},
    )

    result = await _call("prompts/get", params)

    body = " ".join(
        message.content.text
        for message in result.messages
        if isinstance(message.content, types.TextContent)
    )
    assert _BILLING_MONTH in body
    assert "Notion" in body
    assert "read-only" in body.lower()


async def test_get_prompt_rejects_unknown_name() -> None:
    params = types.GetPromptRequestParams(name="nope", arguments={})

    with pytest.raises(MCPError):
        await _call("prompts/get", params)


async def test_completion_suggests_seeded_bill_ids(seeded_bill_id: int) -> None:
    params = types.CompleteRequestParams(
        ref=types.ResourceTemplateReference(
            type="ref/resource", uri=_BILL_URI_TEMPLATE
        ),
        argument=types.CompletionArgument(name="bill_id", value=""),
    )

    result = await _call("completion/complete", params)

    assert str(seeded_bill_id) in result.completion.values


async def test_completion_suggests_billing_months_for_prompt_argument(
    seeded_bill_id: int,
) -> None:
    params = types.CompleteRequestParams(
        ref=types.PromptReference(type="ref/prompt", name="reconcile_with_notion"),
        argument=types.CompletionArgument(name="month", value=""),
    )

    result = await _call("completion/complete", params)

    assert result.completion.values == [_BILLING_MONTH]


async def test_completion_of_unknown_argument_is_empty(seeded_bill_id: int) -> None:
    params = types.CompleteRequestParams(
        ref=types.PromptReference(type="ref/prompt", name="reconcile_with_notion"),
        argument=types.CompletionArgument(name="unknown", value=""),
    )

    result = await _call("completion/complete", params)

    assert result.completion.values == []


async def test_discover_advertises_the_new_capabilities() -> None:
    result = await _call("server/discover", types.RequestParams())

    capabilities = result.capabilities
    assert capabilities.tools is not None
    assert capabilities.resources is not None
    assert capabilities.prompts is not None
    assert capabilities.completions is not None
    # The existing contract: never advertise change notifications we do not send.
    assert capabilities.resources.list_changed is None
    assert capabilities.resources.subscribe is None
    assert capabilities.prompts.list_changed is None
