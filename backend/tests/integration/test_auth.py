"""Bearer Token 認證 middleware 測試。"""

from httpx import AsyncClient

from tests.integration.conftest import TEST_TOKEN, auth_headers


async def test_valid_token_passes(client: AsyncClient):
    """帶有效 Token 的請求正常通過。"""
    response = await client.get("/api/overview", headers=auth_headers())
    assert response.status_code == 200


async def test_missing_token_returns_401(client: AsyncClient):
    """缺少 Token 的請求回傳 401。"""
    response = await client.get("/api/overview")
    assert response.status_code == 401


async def test_invalid_token_returns_401(client: AsyncClient):
    """無效 Token 的請求回傳 401。"""
    response = await client.get("/api/overview", headers=auth_headers("wrong-token"))
    assert response.status_code == 401


async def test_session_cookie_passes_without_bearer_header(client: AsyncClient):
    """瀏覽器 session cookie 可取代 Authorization header。"""
    login = await client.post("/api/auth/session", json={"token": TEST_TOKEN})
    assert login.status_code == 204

    response = await client.get("/api/overview")
    assert response.status_code == 200


async def test_invalid_session_login_returns_401(client: AsyncClient):
    """錯誤 token 建立 session 應回傳 401。"""
    response = await client.post("/api/auth/session", json={"token": "wrong-token"})
    assert response.status_code == 401


async def test_logout_clears_session_cookie(client: AsyncClient):
    """登出後 cookie session 不可再存取 API。"""
    login = await client.post("/api/auth/session", json={"token": TEST_TOKEN})
    assert login.status_code == 204

    logout = await client.delete("/api/auth/session")
    assert logout.status_code == 204

    response = await client.get("/api/overview")
    assert response.status_code == 401


async def test_get_session_status_reflects_current_cookie(client: AsyncClient):
    """session status 端點會反映目前登入狀態。"""
    unauthenticated = await client.get("/api/auth/session")
    assert unauthenticated.status_code == 200
    assert unauthenticated.json()["data"]["authenticated"] is False

    login = await client.post("/api/auth/session", json={"token": TEST_TOKEN})
    assert login.status_code == 204

    authenticated = await client.get("/api/auth/session")
    assert authenticated.status_code == 200
    assert authenticated.json()["data"]["authenticated"] is True


async def test_health_no_auth_required(client: AsyncClient):
    """健康檢查端點不需認證。"""
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
