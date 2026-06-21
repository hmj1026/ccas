"""健康檢查端點整合測試。

``/health`` 為純 liveness；``/health/ready`` 實際探測 DB 與 Redis，
任一依賴失敗回 503 degraded。
"""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from redis.exceptions import RedisError
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession


async def test_health_returns_ok(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_health_ready_ok(client: AsyncClient):
    """DB 與 Redis 皆可達時回 200 ok。"""
    mock_redis = AsyncMock()
    with patch("ccas.api.app.AsyncRedis") as redis_cls:
        redis_cls.from_url.return_value = mock_redis
        response = await client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "ok", "redis": "ok"}
    mock_redis.ping.assert_awaited_once()
    mock_redis.aclose.assert_awaited_once()


async def test_api_health_ready_alias(client: AsyncClient):
    """``/api/health/ready`` 為反向代理 passthrough 別名，行為同 ``/health/ready``。"""
    mock_redis = AsyncMock()
    with patch("ccas.api.app.AsyncRedis") as redis_cls:
        redis_cls.from_url.return_value = mock_redis
        response = await client.get("/api/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "ok", "redis": "ok"}


async def test_health_ready_redis_down_returns_503(client: AsyncClient):
    """Redis ping 失敗時回 503 degraded。"""
    mock_redis = AsyncMock()
    mock_redis.ping.side_effect = RedisError("connection refused")
    with patch("ccas.api.app.AsyncRedis") as redis_cls:
        redis_cls.from_url.return_value = mock_redis
        response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "db": "ok", "redis": "error"}
    mock_redis.aclose.assert_awaited_once()


async def test_health_ready_db_down_returns_503(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
):
    """DB SELECT 1 失敗時回 503 degraded。"""

    async def _failing_execute(*args: object, **kwargs: object) -> None:
        raise OperationalError("SELECT 1", None, Exception("db down"))

    monkeypatch.setattr(db_session, "execute", _failing_execute)
    mock_redis = AsyncMock()
    with patch("ccas.api.app.AsyncRedis") as redis_cls:
        redis_cls.from_url.return_value = mock_redis
        response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "db": "error", "redis": "ok"}
