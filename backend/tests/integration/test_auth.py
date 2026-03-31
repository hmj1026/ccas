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


async def test_health_no_auth_required(client: AsyncClient):
    """健康檢查端點不需認證。"""
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
