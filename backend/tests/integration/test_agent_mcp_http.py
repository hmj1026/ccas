"""Wire-contract tests for loopback Streamable HTTP MCP.

These tests drive the public HTTP seam (``POST /mcp``): Bearer auth, cookie
rejection, tools/list parity with stdio, Streamable HTTP entry, and
DNS-rebinding Host rejection.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Generator, Mapping
from contextlib import asynccontextmanager
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient, Response
from starlette.applications import Starlette

from ccas.api.deps import current_api_token_version, encode_session_cookie
from ccas.config import get_settings
from ccas.mcp.http import create_http_app
from tests.integration.conftest import TEST_TOKEN, auth_headers

_MCP_PATH = "/mcp"
_PROTOCOL_VERSION = "2026-07-28"
_LOOPBACK_BASE_URL = "http://127.0.0.1:8001"
_LOOPBACK_HOST = "127.0.0.1:8001"
_ILLEGAL_HOST = "evil.example:8001"
_DEPRECATED_SSE_PATH = "/sse"
_DEPRECATED_MESSAGE_PATHS = ("/messages", "/messages/")
_READ_TOOLS = (
    "list_bills",
    "get_bill",
    "query_transactions",
    "get_payment_due",
    "budget_status",
    "pipeline_status",
)
_UNAUTHORIZED = 401
_INVALID_HOST = 421


@pytest.fixture(autouse=True)
def _loopback_mcp_http_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[None, None, None]:
    monkeypatch.setenv("MCP_HTTP_HOST", "127.0.0.1")
    monkeypatch.setenv("MCP_HTTP_PORT", "8001")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@asynccontextmanager
async def _mcp_http_client() -> AsyncIterator[AsyncClient]:
    """Open Streamable HTTP lifespan in the same task as the test body.

    An async pytest fixture yields across a task boundary; the SDK's anyio
    cancel scope then errors on teardown. Keep enter/exit in one task.
    """
    app = create_http_app()
    assert isinstance(app, Starlette)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url=_LOOPBACK_BASE_URL,
        ) as client:
            yield client


def _tools_list_body() -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/list",
        "params": {
            "_meta": {
                "io.modelcontextprotocol/protocolVersion": _PROTOCOL_VERSION,
                "io.modelcontextprotocol/clientCapabilities": {},
            }
        },
    }


def _mcp_headers(
    extra: Mapping[str, str] | None = None,
    *,
    host: str = _LOOPBACK_HOST,
) -> dict[str, str]:
    headers = {
        "Host": host,
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        "MCP-Protocol-Version": _PROTOCOL_VERSION,
        "MCP-Method": "tools/list",
    }
    if extra:
        headers.update(extra)
    return headers


async def _post_tools_list(
    client: AsyncClient,
    extra_headers: Mapping[str, str] | None = None,
    *,
    host: str = _LOOPBACK_HOST,
) -> Response:
    return await client.post(
        _MCP_PATH,
        headers=_mcp_headers(extra_headers, host=host),
        json=_tools_list_body(),
    )


def _header_names(response: Response) -> set[str]:
    return {name.lower() for name in response.headers}


def _assert_rejected_without_mcp_session(
    response: Response,
    *,
    status_code: int,
) -> None:
    assert response.status_code == status_code
    assert "mcp-session-id" not in _header_names(response)
    assert "list_bills" not in response.text


def _jsonrpc_from_http(response: Response) -> dict[str, Any]:
    content_type = response.headers.get("content-type", "")
    if content_type.startswith("text/event-stream"):
        for line in response.text.splitlines():
            if line.startswith("data:"):
                payload = json.loads(line.removeprefix("data:").strip())
                if isinstance(payload, dict):
                    return payload
        raise AssertionError("SSE body had no JSON-RPC data event")
    payload = response.json()
    assert isinstance(payload, dict)
    return payload


async def test_http_mcp_missing_bearer_returns_401() -> None:
    async with _mcp_http_client() as client:
        response = await _post_tools_list(client)

    _assert_rejected_without_mcp_session(response, status_code=_UNAUTHORIZED)


async def test_http_mcp_session_cookie_without_bearer_returns_401() -> None:
    cookie_name = get_settings().api_session_cookie_name
    cookie_value = encode_session_cookie(
        TEST_TOKEN,
        current_api_token_version(),
    )

    async with _mcp_http_client() as client:
        response = await _post_tools_list(
            client,
            {"Cookie": f"{cookie_name}={cookie_value}"},
        )

    _assert_rejected_without_mcp_session(response, status_code=_UNAUTHORIZED)


async def test_http_mcp_invalid_bearer_returns_401() -> None:
    async with _mcp_http_client() as client:
        response = await _post_tools_list(
            client,
            auth_headers("wrong-token"),
        )

    _assert_rejected_without_mcp_session(response, status_code=_UNAUTHORIZED)


async def test_http_mcp_valid_bearer_lists_the_same_six_read_tools_as_stdio() -> None:
    async with _mcp_http_client() as client:
        response = await _post_tools_list(client, auth_headers())

    assert response.status_code == 200
    assert "mcp-session-id" not in _header_names(response)
    payload = _jsonrpc_from_http(response)
    assert "error" not in payload
    tools = payload["result"]["tools"]
    assert [tool["name"] for tool in tools] == list(_READ_TOOLS)


async def test_http_mcp_uses_streamable_http_entry_not_deprecated_sse_pair() -> None:
    async with _mcp_http_client() as client:
        mcp = await _post_tools_list(client, auth_headers())
        assert mcp.status_code != 404

        sse = await client.get(
            _DEPRECATED_SSE_PATH,
            headers=_mcp_headers(auth_headers()),
        )
        assert sse.status_code == 404

        for path in _DEPRECATED_MESSAGE_PATHS:
            posted = await client.post(
                path,
                headers=_mcp_headers(auth_headers()),
                json=_tools_list_body(),
            )
            assert posted.status_code == 404


async def test_http_mcp_illegal_host_is_rejected() -> None:
    async with _mcp_http_client() as client:
        response = await _post_tools_list(
            client,
            auth_headers(),
            host=_ILLEGAL_HOST,
        )

    _assert_rejected_without_mcp_session(response, status_code=_INVALID_HOST)


async def test_http_mcp_does_not_expose_oauth_resource_metadata() -> None:
    async with _mcp_http_client() as client:
        response = await client.get(
            "/.well-known/oauth-protected-resource/mcp",
            headers=_mcp_headers(auth_headers()),
        )

    assert response.status_code == 404
