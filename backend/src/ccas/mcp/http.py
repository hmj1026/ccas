"""Loopback Streamable HTTP adapter for the read-only Agent MCP server.

stdio remains in ``ccas.mcp.server``. This module owns HTTP bind, Bearer
auth, and the official Streamable HTTP ASGI app. Loopback enforcement lives
here rather than on Settings so a stray ``MCP_HTTP_HOST=0.0.0.0`` cannot
fail worker or REST API processes that share ``get_settings()``.
"""

from __future__ import annotations

from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import AnyHttpUrl, TypeAdapter
from starlette.types import ASGIApp

from ccas.api.deps import is_valid_api_token
from ccas.config import get_settings
from ccas.mcp.server import create_server

_LOOPBACK_HOSTS: frozenset[str] = frozenset({"127.0.0.1", "::1", "localhost"})
_STREAMABLE_HTTP_PATH = "/mcp"
_HTTP_URL = TypeAdapter(AnyHttpUrl)


def _require_loopback_host(host: str) -> str:
    """Reject non-loopback bind addresses before the process listens."""
    if host not in _LOOPBACK_HOSTS:
        raise ValueError(f"MCP HTTP bind host must be loopback, got {host!r}")
    return host


def _loopback_resource_url(host: str, port: int) -> AnyHttpUrl:
    authority = f"[{host}]:{port}" if ":" in host else f"{host}:{port}"
    return _HTTP_URL.validate_python(f"http://{authority}{_STREAMABLE_HTTP_PATH}")


class _ApiTokenVerifier:
    """Verify MCP HTTP Bearer tokens against the live REST API token."""

    async def verify_token(self, token: str) -> AccessToken | None:
        if not is_valid_api_token(token):
            return None
        return AccessToken(
            token=token,
            client_id="ccas-mcp-http",
            scopes=[],
        )


def create_http_app() -> ASGIApp:
    """Build the loopback Streamable HTTP ASGI app, or refuse to start."""
    settings = get_settings()
    host = _require_loopback_host(settings.mcp_http_host)
    port = settings.mcp_http_port
    resource_url = _loopback_resource_url(host, port)
    server = create_server()
    return server.streamable_http_app(
        streamable_http_path=_STREAMABLE_HTTP_PATH,
        host=host,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=["127.0.0.1:*", "localhost:*", "[::1]:*"],
            allowed_origins=[
                "http://127.0.0.1:*",
                "http://localhost:*",
                "http://[::1]:*",
            ],
        ),
        auth=AuthSettings(
            issuer_url=resource_url,
            resource_server_url=None,
            required_scopes=[],
            validate_token_resource=False,
        ),
        token_verifier=_ApiTokenVerifier(),
    )


def run_http() -> None:
    """Serve the loopback Streamable HTTP MCP adapter with uvicorn."""
    import uvicorn

    settings = get_settings()
    host = _require_loopback_host(settings.mcp_http_host)
    uvicorn.run(
        "ccas.mcp.http:create_http_app",
        factory=True,
        host=host,
        port=settings.mcp_http_port,
    )


def main() -> None:
    """Console entry point for ``ccas-mcp-http``."""
    run_http()


if __name__ == "__main__":  # pragma: no cover - exercised by the console script
    main()


__all__ = ["create_http_app", "main", "run_http"]
