"""Auth session router 整合測試。

驗證 ``DELETE /api/auth/session`` 在 router-level ``verify_token`` 依賴下
對各種認證狀態的行為差異（401 vs 204）。此處用整合測試（經由 FastAPI
routing / middleware）而非單元測試，是因為 route-level ``dependencies=``
只在實際 routing 流程中觸發；直接呼叫 router 函式會繞過依賴注入。
"""

from __future__ import annotations

from httpx import AsyncClient

from ccas.config import get_settings
from tests.integration.conftest import TEST_TOKEN, auth_headers

# Derive cookie name from Settings so the tests stay correct if the default
# ever changes（reviewer SHOULD-FIX: 避免 hardcode 值與 Settings 脫鉤）。
_COOKIE_NAME = get_settings().api_session_cookie_name


async def test_delete_session_requires_auth(client: AsyncClient):
    """沒有 cookie 也沒有 Bearer token → 401。"""
    resp = await client.delete("/api/auth/session")
    assert resp.status_code == 401


async def test_delete_session_with_bearer_clears_cookie(client: AsyncClient):
    """帶 Bearer token → 204 + Set-Cookie 含 Max-Age=0。"""
    resp = await client.delete("/api/auth/session", headers=auth_headers())
    assert resp.status_code == 204
    set_cookie = resp.headers.get("set-cookie", "")
    assert f"{_COOKIE_NAME}=" in set_cookie
    assert "Max-Age=0" in set_cookie


async def test_delete_session_with_cookie_clears_cookie(client: AsyncClient):
    """帶有效 session cookie → 204 + Set-Cookie 含 Max-Age=0。"""
    resp = await client.delete(
        "/api/auth/session",
        headers={"Cookie": f"{_COOKIE_NAME}={TEST_TOKEN}"},
    )
    assert resp.status_code == 204
    set_cookie = resp.headers.get("set-cookie", "")
    assert f"{_COOKIE_NAME}=" in set_cookie
    assert "Max-Age=0" in set_cookie


async def test_delete_session_invalid_cookie_returns_401(client: AsyncClient):
    """cookie 值不匹配 API_TOKEN → 401（不應該意外通過）。"""
    resp = await client.delete(
        "/api/auth/session",
        headers={"Cookie": f"{_COOKIE_NAME}=wrong-token"},
    )
    assert resp.status_code == 401


async def test_api_response_includes_csp_header(client: AsyncClient):
    """API response 應含 Content-Security-Policy（defense in depth）。"""
    resp = await client.get("/api/auth/session")
    assert resp.status_code == 200
    csp = resp.headers.get("content-security-policy", "")
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp


async def test_api_response_includes_baseline_security_headers(client: AsyncClient):
    """API response 應含其餘 baseline security headers（與 CSP 斷言分離，單一關注）。"""
    resp = await client.get("/api/auth/session")
    assert resp.status_code == 200
    assert resp.headers.get("x-content-type-options") == "nosniff"
    assert resp.headers.get("x-frame-options") == "DENY"
    assert resp.headers.get("referrer-policy") == "strict-origin-when-cross-origin"


async def test_openapi_schema_skips_csp_header(client: AsyncClient):
    """/openapi.json（及 /docs、/redoc）不應被 CSP 套住，否則 Swagger UI 壞掉。"""
    resp = await client.get("/openapi.json")
    assert resp.status_code == 200
    assert "content-security-policy" not in {k.lower() for k in resp.headers.keys()}
