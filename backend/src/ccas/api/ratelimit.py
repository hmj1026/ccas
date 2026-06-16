"""Redis-backed login rate limiter (defense-in-depth, Stage 6 Item B).

nginx already throttles ``/api/auth/session`` to 5r/m, but that single layer
disappears in dev (no proxy) and for any future deployment that fronts the API
differently. This module adds an *application-layer* fixed-window failure
counter so a brute-force run against the API token is bounded even without
nginx.

Design
------
- Only **failed** session attempts increment ``login_fail:{client_ip}``; a
  successful login never touches the counter (so a legitimate user typing the
  right token is never penalised).
- The key carries a 60s TTL set on first increment; the window is therefore a
  rolling-ish fixed window of ~1 minute.
- ``THRESHOLD`` failures within the window trips a 429.
- **Fail-open**: any Redis error (unavailable, timeout, misconfig) is caught
  and logged, and the limiter reports "not limited". The rate limiter must
  never become the reason auth is unavailable.

Client IP resolution is **trust-aware** (security-reviewer H1): ``X-Forwarded-For``
is fully client-controlled, so trusting its left-most hop unconditionally lets an
attacker rotate a fake IP per 10 attempts and bypass the limiter entirely. We
therefore only honour XFF when the *socket peer* is a trusted proxy — i.e. a
loopback or private-range address, which is where nginx sits in the compose
network. A direct/public client (dev, or anyone reaching uvicorn without the
proxy) is keyed by its real socket peer and cannot spoof its bucket.
"""

from __future__ import annotations

import ipaddress
import logging
from typing import TYPE_CHECKING, cast

from redis.asyncio import Redis as AsyncRedis
from redis.exceptions import RedisError

from ccas.config import get_settings

if TYPE_CHECKING:
    from collections.abc import Awaitable

    from fastapi import Request

logger = logging.getLogger(__name__)

# Failed attempts allowed per window before a 429 is returned.
LOGIN_FAIL_THRESHOLD = 10
# Fixed-window length in seconds.
LOGIN_FAIL_WINDOW_SECONDS = 60
_KEY_PREFIX = "login_fail:"

# Process-wide async Redis singleton; lazily built. Mirrors the sync singleton
# in ``api.routers.pipeline`` but on the async client (auth endpoints are async).
# No lock is needed: ``AsyncRedis.from_url`` only builds a (stateless) connection
# pool — under the GIL the worst case is two pools built on a concurrent first
# access with the later assignment winning; the unused pool is harmless and is
# never opened. (Contrast MasterKeyManager, which guards real key material.)
_redis: AsyncRedis | None = None


def _peer_is_trusted_proxy(request: Request) -> bool:
    """True when the socket peer is a loopback/private address (i.e. our nginx).

    Only such a peer is allowed to dictate the client IP via ``X-Forwarded-For``.
    A public/direct peer is keyed by its own socket address instead, so it cannot
    forge an XFF value to escape its rate-limit bucket.
    """
    if request.client is None:
        return False
    try:
        addr = ipaddress.ip_address(request.client.host)
    except ValueError:
        return False
    return addr.is_loopback or addr.is_private or addr.is_link_local


def _get_redis() -> AsyncRedis:
    """Return the process async Redis client (lazy singleton)."""
    global _redis
    if _redis is None:
        _redis = AsyncRedis.from_url(get_settings().redis_url)
    return _redis


def client_ip(request: Request) -> str:
    """Best-effort original client IP, resisting ``X-Forwarded-For`` spoofing.

    Honours the left-most XFF hop **only** when the socket peer is a trusted
    proxy (loopback/private — our nginx). Otherwise (dev, or a client reaching
    uvicorn directly) the real socket peer is used so XFF cannot be forged to
    dodge the limiter. Returns ``"unknown"`` when no source is available so the
    counter still groups rather than crashing on odd transports.
    """
    if _peer_is_trusted_proxy(request):
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            first = forwarded.split(",", 1)[0].strip()
            # Only honour a syntactically-valid IP. A mis-configured or
            # compromised upstream could relay a non-IP / oversized value that
            # would otherwise become an arbitrary (and unbounded) Redis bucket
            # key; fall back to the real socket peer in that case.
            if first:
                try:
                    ipaddress.ip_address(first)
                except ValueError:
                    pass
                else:
                    return first
    if request.client is not None:
        return request.client.host
    return "unknown"


async def is_login_rate_limited(ip: str) -> bool:
    """Return True when *ip* has too many recent failed login attempts.

    Reads the current counter WITHOUT incrementing (the increment happens on an
    actual failure via :func:`register_login_failure`). Fail-open on any Redis
    error.
    """
    try:
        raw = await cast("Awaitable[object]", _get_redis().get(_KEY_PREFIX + ip))
    except (RedisError, OSError) as exc:
        logger.warning("login rate-limit check skipped (redis error): %s", exc)
        return False
    if raw is None:
        return False
    try:
        count = int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    return count >= LOGIN_FAIL_THRESHOLD


async def register_login_failure(ip: str) -> None:
    """Increment the failure counter for *ip*, setting the window TTL once.

    INCR + a conditional EXPIRE are issued in one context-managed pipeline.
    The TTL is set **only when the counter first reaches 1** (security-reviewer
    M2): refreshing the TTL on every failure would let an attacker pace just
    under the threshold forever without the key ever expiring. ``EXPIRE NX``
    sets the TTL only when none exists, so a steady stream of failures within
    the original 60s window cannot extend it. Fail-open: a Redis error is logged
    and swallowed so a failed *login* is never turned into a failed *request*.
    """
    key = _KEY_PREFIX + ip
    try:
        async with _get_redis().pipeline() as pipe:
            pipe.incr(key)
            # nx=True → only set the expiry when the key has none yet, so the
            # window is anchored to the first failure and never slides forward.
            pipe.expire(key, LOGIN_FAIL_WINDOW_SECONDS, nx=True)
            await cast("Awaitable[object]", pipe.execute())
    except (RedisError, OSError) as exc:
        logger.warning("login failure counter not recorded (redis error): %s", exc)
