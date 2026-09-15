"""MCP HTTP Settings defaults and loopback bind fail-closed.

Loopback enforcement belongs on ``create_http_app()``, not on Settings
validators: ``get_settings()`` is imported across workers and the REST API,
so a stray ``MCP_HTTP_HOST=0.0.0.0`` must not prevent those processes from
starting.
"""

from __future__ import annotations

import pytest

from ccas.config import Settings, get_settings

_DEFAULT_MCP_HTTP_HOST = "127.0.0.1"
_DEFAULT_MCP_HTTP_PORT = 8001
_ALL_INTERFACES_HOST = "0.0.0.0"
_LOOPBACK_HOSTS = ("127.0.0.1", "::1", "localhost")
_NON_LOOPBACK_HOSTS = ("0.0.0.0", "192.168.1.10", "::")


def _clear_mcp_http_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MCP_HTTP_HOST", raising=False)
    monkeypatch.delenv("MCP_HTTP_PORT", raising=False)
    monkeypatch.delenv("MCP_OAUTH_ISSUER_URL", raising=False)


def test_mcp_http_host_defaults_to_loopback_ipv4(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_mcp_http_env(monkeypatch)
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]

    assert settings.mcp_http_host == _DEFAULT_MCP_HTTP_HOST


def test_mcp_http_port_defaults_to_8001(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_mcp_http_env(monkeypatch)
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]

    assert settings.mcp_http_port == _DEFAULT_MCP_HTTP_PORT


def test_get_settings_accepts_mcp_http_host_all_interfaces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MCP_HTTP_HOST", _ALL_INTERFACES_HOST)
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.mcp_http_host == _ALL_INTERFACES_HOST
    finally:
        get_settings.cache_clear()


@pytest.mark.parametrize("host", _NON_LOOPBACK_HOSTS)
def test_create_http_app_refuses_non_loopback_bind(
    monkeypatch: pytest.MonkeyPatch,
    host: str,
) -> None:
    monkeypatch.setenv("MCP_HTTP_HOST", host)
    get_settings.cache_clear()
    try:
        from ccas.mcp.http import create_http_app

        with pytest.raises(ValueError) as exc_info:
            create_http_app()
        message = str(exc_info.value)
        assert "loopback" in message.lower()
        assert repr(host) in message
    finally:
        get_settings.cache_clear()


@pytest.mark.parametrize("host", _LOOPBACK_HOSTS)
def test_create_http_app_allows_loopback_bind(
    monkeypatch: pytest.MonkeyPatch,
    host: str,
) -> None:
    monkeypatch.setenv("MCP_HTTP_HOST", host)
    get_settings.cache_clear()
    try:
        from ccas.mcp.http import create_http_app

        create_http_app()
    except ValueError as exc:
        pytest.fail(f"loopback host {host!r} must be accepted, got {exc}")
    finally:
        get_settings.cache_clear()


def test_mcp_oauth_issuer_url_defaults_to_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Static-Bearer stays the default; discovery is opt-in."""
    _clear_mcp_http_env(monkeypatch)
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]

    assert settings.mcp_oauth_issuer_url == ""


def test_create_http_app_rejects_non_http_oauth_issuer_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A malformed issuer must fail at startup, not silently disable discovery."""
    monkeypatch.setenv("MCP_HTTP_HOST", _DEFAULT_MCP_HTTP_HOST)
    monkeypatch.setenv("MCP_OAUTH_ISSUER_URL", "not-a-url")
    get_settings.cache_clear()
    try:
        from ccas.mcp.http import create_http_app

        with pytest.raises(ValueError):
            create_http_app()
    finally:
        get_settings.cache_clear()


async def test_audience_validation_tracks_the_token_verifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tie ``validate_token_resource`` to what the token verifier reports.

    ``_auth_settings`` hardcodes ``validate_token_resource=False`` because
    ``_ApiTokenVerifier`` compares a static shared secret and never populates
    ``AccessToken.resource``. The day that verifier is replaced with real
    OAuth/JWT verification against ``MCP_OAUTH_ISSUER_URL``, leaving the flag
    at ``False`` would silently accept tokens an authorization server issued
    for a *different* resource (RFC 8707 audience confusion). This test fails
    at exactly that moment instead of letting the pair drift apart.
    """
    from pydantic import AnyHttpUrl, TypeAdapter

    import ccas.mcp.http as mcp_http

    monkeypatch.setattr(mcp_http, "is_valid_api_token", lambda _token: True)
    granted = await mcp_http._ApiTokenVerifier().verify_token("any-accepted-token")
    assert granted is not None

    if granted.resource is None:
        return

    resource_url = TypeAdapter(AnyHttpUrl).validate_python("http://127.0.0.1:8001/mcp")
    settings = mcp_http._auth_settings(resource_url, "https://auth.example.com")
    assert settings.validate_token_resource is True, (
        "the token verifier now reports an RFC 8707 resource indicator; "
        "_auth_settings must validate it instead of hardcoding False"
    )
