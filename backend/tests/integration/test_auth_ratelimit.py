"""Login rate-limit defense-in-depth tests (Stage 6 Item B).

Covers the app-layer Redis failure counter on ``POST /api/auth/session``:
threshold trips a 429, a successful login never counts, and a Redis outage
fails OPEN (login still processes). Redis is mocked — these tests assert the
limiter's control flow, not a live Redis.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from redis.exceptions import RedisError

from ccas.api import ratelimit
from tests.integration.conftest import TEST_TOKEN

if TYPE_CHECKING:
    from collections.abc import Generator


@pytest.fixture(autouse=True)
def _reset_redis_singleton() -> Generator[None, None, None]:
    """Drop the module-level async Redis singleton between tests."""
    ratelimit._redis = None
    yield
    ratelimit._redis = None


def _make_pipe(*, execute: AsyncMock) -> MagicMock:
    """Build a MagicMock pipeline that works as an async context manager."""
    pipe = MagicMock()
    pipe.incr = MagicMock()
    pipe.expire = MagicMock()
    pipe.execute = execute
    # ``async with redis.pipeline() as pipe`` → __aenter__ returns the pipe.
    pipe.__aenter__ = AsyncMock(return_value=pipe)
    pipe.__aexit__ = AsyncMock(return_value=False)
    return pipe


def _mock_redis(*, count: int) -> MagicMock:
    """Build an AsyncMock Redis whose GET returns *count* and supports pipeline."""
    redis = MagicMock()
    redis.get = AsyncMock(return_value=str(count).encode())
    pipe = _make_pipe(execute=AsyncMock(return_value=[count + 1, True]))
    redis.pipeline = MagicMock(return_value=pipe)
    return redis


async def test_over_threshold_returns_429(client: AsyncClient) -> None:
    """Counter at/above threshold → 429 in the ApiResponse envelope."""
    redis = _mock_redis(count=ratelimit.LOGIN_FAIL_THRESHOLD)
    with patch.object(ratelimit, "_get_redis", return_value=redis):
        resp = await client.post(
            "/api/auth/session",
            json={"token": "wrong-token"},
            headers={"X-Forwarded-For": "203.0.113.7"},
        )
    assert resp.status_code == 429
    body = resp.json()
    assert body["success"] is False
    assert body["data"] is None
    assert body["message"]
    # Blocked before token validation: GET checked, no further INCR this call.
    redis.get.assert_awaited_once()


async def test_failed_attempt_increments_counter(client: AsyncClient) -> None:
    """A bad token under threshold returns 401 AND records a failure."""
    redis = _mock_redis(count=0)
    with patch.object(ratelimit, "_get_redis", return_value=redis):
        resp = await client.post(
            "/api/auth/session",
            json={"token": "wrong-token"},
            headers={"X-Forwarded-For": "203.0.113.8"},
        )
    assert resp.status_code == 401
    redis.pipeline.return_value.incr.assert_called_once()
    # TTL is anchored to the first failure via EXPIRE ... NX (security-reviewer M2).
    redis.pipeline.return_value.expire.assert_called_once_with(
        "login_fail:203.0.113.8", ratelimit.LOGIN_FAIL_WINDOW_SECONDS, nx=True
    )


async def test_successful_login_does_not_increment(client: AsyncClient) -> None:
    """A correct token never touches the failure counter."""
    redis = _mock_redis(count=0)
    with patch.object(ratelimit, "_get_redis", return_value=redis):
        resp = await client.post(
            "/api/auth/session",
            json={"token": TEST_TOKEN},
            headers={"X-Forwarded-For": "203.0.113.9"},
        )
    assert resp.status_code == 204
    redis.pipeline.return_value.incr.assert_not_called()


async def test_redis_unavailable_fails_open(client: AsyncClient) -> None:
    """If Redis errors, the limiter must NOT block — login still processes."""
    redis = MagicMock()
    redis.get = AsyncMock(side_effect=RedisError("connection refused"))
    pipe = _make_pipe(execute=AsyncMock(side_effect=RedisError("connection refused")))
    redis.pipeline = MagicMock(return_value=pipe)

    with patch.object(ratelimit, "_get_redis", return_value=redis):
        # Valid token still succeeds despite the rate-limit check erroring.
        ok = await client.post("/api/auth/session", json={"token": TEST_TOKEN})
        # Invalid token still gets a normal 401 (not a 429 or 500).
        bad = await client.post("/api/auth/session", json={"token": "wrong-token"})

    assert ok.status_code == 204
    assert bad.status_code == 401


async def test_client_ip_trusts_forwarded_for_from_private_peer() -> None:
    """XFF left-most hop wins when the socket peer is our (private) nginx."""
    request = MagicMock()
    request.headers = {"x-forwarded-for": "198.51.100.5, 10.0.0.1"}
    request.client = MagicMock(host="10.0.0.1")  # private → trusted proxy
    assert ratelimit.client_ip(request) == "198.51.100.5"


async def test_client_ip_ignores_forwarded_for_from_public_peer() -> None:
    """A public/direct client cannot spoof XFF to dodge the bucket (H1).

    8.8.8.8 is a genuinely global address (unlike the TEST-NET doc ranges, which
    ``ipaddress`` marks private), so the peer is untrusted and XFF is ignored.
    """
    request = MagicMock()
    request.headers = {"x-forwarded-for": "10.0.0.1"}  # attacker-supplied
    request.client = MagicMock(host="8.8.8.8")  # public peer → untrusted
    assert ratelimit.client_ip(request) == "8.8.8.8"


async def test_client_ip_falls_back_to_peer() -> None:
    request = MagicMock()
    request.headers = {}
    request.client = MagicMock(host="192.0.2.50")
    assert ratelimit.client_ip(request) == "192.0.2.50"
