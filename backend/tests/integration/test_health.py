"""健康檢查端點整合測試。"""

from httpx import AsyncClient


async def test_health_returns_ok(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
