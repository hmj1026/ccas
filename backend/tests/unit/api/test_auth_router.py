"""Session auth router 單元測試。"""

from pathlib import Path

import pytest
from fastapi import Response
from starlette.requests import Request

from ccas.api.deps import (
    current_api_token_version,
    decode_session_cookie,
    encode_session_cookie,
    is_valid_session_cookie,
)
from ccas.api.routers.auth import create_session, delete_session, get_session_status
from ccas.api.schemas import SessionLoginRequest
from ccas.config import get_settings


@pytest.fixture(autouse=True)
def _master_key_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Point master.key at tmp_path so cookie signing never touches repo data."""
    monkeypatch.setenv("MASTER_KEY_PATH", str(tmp_path / "master.key"))
    get_settings.cache_clear()


def _make_request(cookie_header: str | None = None) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if cookie_header is not None:
        headers.append((b"cookie", cookie_header.encode()))
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/auth/session",
        "headers": headers,
    }
    return Request(scope)


class TestAuthRouter:
    async def test_get_session_status_detects_valid_cookie(self, monkeypatch):
        monkeypatch.setenv("API_TOKEN", "test-token")
        get_settings.cache_clear()
        cookie_value = encode_session_cookie("test-token", current_api_token_version())

        response = await get_session_status(
            _make_request(f"ccas_session={cookie_value}")
        )

        assert response.data.authenticated is True

    async def test_create_session_sets_http_only_cookie(self, monkeypatch):
        monkeypatch.setenv("API_TOKEN", "test-token")
        get_settings.cache_clear()

        request = _make_request()
        response = Response()
        await create_session(request, SessionLoginRequest(token="test-token"), response)

        set_cookie = response.headers["set-cookie"]
        # Cookie value is opaque ({version}.{timestamp}.{hmac}); the
        # plaintext API token must never appear in the Set-Cookie header.
        assert "test-token" not in set_cookie
        prefix = "ccas_session="
        start = set_cookie.index(prefix) + len(prefix)
        end = set_cookie.index(";", start)
        cookie_value = set_cookie[start:end]
        decoded = decode_session_cookie(cookie_value)
        assert decoded is not None
        version, _issued_at, _mac = decoded
        assert version == current_api_token_version()
        assert is_valid_session_cookie(cookie_value)
        assert "HttpOnly" in set_cookie
        assert "SameSite=lax" in set_cookie

    async def test_delete_session_clears_cookie(self, monkeypatch):
        monkeypatch.setenv("API_TOKEN", "test-token")
        get_settings.cache_clear()

        response = Response()
        await delete_session(response)

        set_cookie = response.headers["set-cookie"]
        assert "ccas_session=" in set_cookie
        assert "Max-Age=0" in set_cookie
        assert "SameSite=lax" in set_cookie
