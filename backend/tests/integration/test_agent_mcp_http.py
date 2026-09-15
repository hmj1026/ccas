"""Wire-contract tests for loopback Streamable HTTP MCP.

These tests drive the public HTTP seam (``POST /mcp``): Bearer auth, cookie
rejection, tools/list parity with stdio, Streamable HTTP entry, and
DNS-rebinding Host rejection.
"""

from __future__ import annotations

import json
import os
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


def _build_app() -> Starlette:
    app = create_http_app()
    assert isinstance(app, Starlette)
    return app


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
_RESOURCE_METADATA_PATH = "/.well-known/oauth-protected-resource/mcp"
_ISSUER_URL = "https://auth.example.com"
_TOOLS_LIST_TTL_MS = 300_000


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
async def _mcp_http_client(
    *,
    oauth_issuer_url: str | None = None,
) -> AsyncIterator[AsyncClient]:
    """Open Streamable HTTP lifespan in the same task as the test body.

    An async pytest fixture yields across a task boundary; the SDK's anyio
    cancel scope then errors on teardown. Keep enter/exit in one task.

    ``oauth_issuer_url`` builds the app with ``MCP_OAUTH_ISSUER_URL`` set, the
    opt-in that turns CCAS into a discoverable OAuth resource server.
    """
    if oauth_issuer_url is not None:
        os.environ["MCP_OAUTH_ISSUER_URL"] = oauth_issuer_url
        get_settings.cache_clear()
    try:
        app = _build_app()
    finally:
        if oauth_issuer_url is not None:
            os.environ.pop("MCP_OAUTH_ISSUER_URL", None)
            get_settings.cache_clear()
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
            _RESOURCE_METADATA_PATH,
            headers=_mcp_headers(auth_headers()),
        )

    assert response.status_code == 404


async def test_http_mcp_401_omits_resource_metadata_without_issuer() -> None:
    """Without an authorization server there is nothing honest to point at.

    The bare ``Bearer`` challenge still ships; what must not appear is a
    ``resource_metadata`` pointer to a discovery document that does not exist.
    """
    async with _mcp_http_client() as client:
        response = await _post_tools_list(client)

    assert response.status_code == _UNAUTHORIZED
    assert "resource_metadata" not in response.headers.get("WWW-Authenticate", "")


async def test_http_mcp_publishes_resource_metadata_when_issuer_configured() -> None:
    async with _mcp_http_client(oauth_issuer_url=_ISSUER_URL) as client:
        response = await client.get(
            _RESOURCE_METADATA_PATH,
            headers=_mcp_headers(auth_headers()),
        )

    assert response.status_code == 200
    metadata = response.json()
    assert metadata["resource"] == f"{_LOOPBACK_BASE_URL}{_MCP_PATH}"
    assert metadata["authorization_servers"] == [_ISSUER_URL]


async def test_http_mcp_401_points_at_resource_metadata_with_issuer() -> None:
    async with _mcp_http_client(oauth_issuer_url=_ISSUER_URL) as client:
        response = await _post_tools_list(client)

    assert response.status_code == _UNAUTHORIZED
    challenge = response.headers["WWW-Authenticate"]
    assert challenge.startswith("Bearer ")
    assert f'resource_metadata="{_LOOPBACK_BASE_URL}{_RESOURCE_METADATA_PATH}"' in (
        challenge
    )


async def test_http_mcp_valid_bearer_still_works_when_issuer_configured() -> None:
    """The opt-in adds discovery; it must not break the static-token path."""
    async with _mcp_http_client(oauth_issuer_url=_ISSUER_URL) as client:
        response = await _post_tools_list(client, auth_headers())

    assert response.status_code == 200
    payload = _jsonrpc_from_http(response)
    assert "error" not in payload
    assert [tool["name"] for tool in payload["result"]["tools"]] == list(_READ_TOOLS)


@pytest.mark.parametrize(
    "method",
    [
        "server/discover",
        "tools/list",
        "prompts/list",
        "resources/list",
        "resources/templates/list",
    ],
)
async def test_http_mcp_static_list_methods_carry_cache_freshness_hints(
    method: str,
) -> None:
    """Drive the real dispatcher: `server/discover` is registered through
    `add_request_handler` rather than an `on_*` callback, so only an
    end-to-end call proves the constructor-level hint actually reaches it."""
    body = _tools_list_body()
    body["method"] = method

    async with _mcp_http_client() as client:
        response = await client.post(
            _MCP_PATH,
            headers=_mcp_headers(auth_headers() | {"MCP-Method": method}),
            json=body,
        )

    payload = _jsonrpc_from_http(response)
    assert "error" not in payload, payload
    result = payload["result"]
    assert result["ttlMs"] == _TOOLS_LIST_TTL_MS
    assert result["cacheScope"] == "private"
