"""Session auth router 單元測試。"""

from fastapi import Response
from starlette.requests import Request

from ccas.api.routers.auth import create_session, delete_session, get_session_status
from ccas.api.schemas import SessionLoginRequest
from ccas.config import get_settings


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

        response = await get_session_status(_make_request("ccas_session=test-token"))

        assert response.data.authenticated is True

    async def test_create_session_sets_http_only_cookie(self, monkeypatch):
        monkeypatch.setenv("API_TOKEN", "test-token")
        get_settings.cache_clear()

        request = _make_request()
        response = Response()
        await create_session(request, SessionLoginRequest(token="test-token"), response)

        set_cookie = response.headers["set-cookie"]
        assert "ccas_session=test-token" in set_cookie
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
