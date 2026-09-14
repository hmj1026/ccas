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
