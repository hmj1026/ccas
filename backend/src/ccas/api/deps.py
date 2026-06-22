"""API 共用依賴：認證、共用查詢參數。"""

import hashlib
import hmac
import logging
import re
import secrets
import time
from dataclasses import dataclass
from datetime import date

from fastapi import Depends, HTTPException, Query, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.config import get_settings
from ccas.storage.database import get_db_session
from ccas.storage.models import Bill

logger = logging.getLogger(__name__)

_MONTH_RE = re.compile(r"^\d{4}-(?:0[1-9]|1[0-2])$")
_bearer_scheme = HTTPBearer(auto_error=False)


def current_api_token() -> str:
    """Read the live API token, preferring the on-disk secrets file.

    The entrypoint writes ``secrets/api-token`` and the rotate endpoint
    overwrites it; reading from the file each call avoids lru_cache from
    pinning a stale value. Falls back to ``Settings.api_token`` (env-loaded)
    when the file is absent — covers dev/test runs that never go through the
    Docker entrypoint.
    """
    settings = get_settings()
    path = settings.api_token_path
    try:
        if path.is_file():
            value = path.read_text().strip()
            if value:
                return value
    except OSError as exc:
        logger.warning("api_token_path read failed: %s", exc)
    return settings.api_token.get_secret_value()


def current_api_token_version() -> int:
    """Read the current token version (defaults to 1 when file absent).

    Used to validate session cookies against the live version: a rotate bumps
    this number, immediately invalidating cookies issued under prior versions.
    """
    settings = get_settings()
    path = settings.api_token_version_path
    try:
        if path.is_file():
            raw = path.read_text().strip()
            if raw:
                return int(raw)
    except (OSError, ValueError) as exc:
        logger.warning("api_token_version_path read failed: %s", exc)
    return 1


def is_valid_api_token(token: str | None) -> bool:
    """檢查 token 是否與目前生效值相符（直接讀檔，不受 lru_cache 影響）。"""
    if not token:
        return False
    return secrets.compare_digest(token, current_api_token())


# Fixed derivation context: the session-signing key is HMAC(master.key,
# context), so it stays independent from the Fernet usage of the same key
# material and needs no extra env var (session-cookie-hmac).
_SESSION_SECRET_CONTEXT = b"ccas-session-v1"


# (path, mtime_ns, derived secret) — self-invalidating: repointing
# MASTER_KEY_PATH (tests) or replacing the key file (rotation) changes the
# cache key, so no explicit reset hook is needed. Nanosecond mtime keeps the
# same-second rotation window negligible on modern filesystems.
_session_secret_cache: tuple[str, int, bytes] | None = None


def _session_secret() -> bytes:
    """Derive the session-cookie signing key from master.key.

    Cached per (path, mtime): authenticated requests verify the cookie on
    every call, so re-reading the key file plus an HMAC derivation each time
    is wasted work. A stat() validates freshness; ``load_or_create``
    auto-generates the key in dev runs that skip the Docker entrypoint.
    """
    global _session_secret_cache
    settings = get_settings()
    key_path = settings.master_key_manager.master_key_path
    try:
        mtime = key_path.stat().st_mtime_ns
    except OSError:
        mtime = -1
    cached = _session_secret_cache
    if cached is not None and cached[0] == str(key_path) and cached[1] == mtime:
        return cached[2]
    master_key = settings.master_key_manager.load_or_create()
    secret = hmac.new(master_key, _SESSION_SECRET_CONTEXT, hashlib.sha256).digest()
    _session_secret_cache = (str(key_path), mtime, secret)
    return secret


def _session_signature(version: int, issued_at: int, token: str) -> str:
    """HMAC-SHA256 hex digest over ``version:timestamp:api_token``."""
    msg = f"{version}:{issued_at}:{token}".encode()
    return hmac.new(_session_secret(), msg, hashlib.sha256).hexdigest()


def encode_session_cookie(
    token: str, version: int, issued_at: int | None = None
) -> str:
    """Build the opaque session cookie: ``{version}.{timestamp}.{hmac}``.

    The HMAC covers ``version:timestamp:api_token`` keyed with a secret
    derived from master.key, so the plaintext API token never appears in the
    cookie. The embedded version lets a token rotate (version bump)
    invalidate every active cookie atomically; the timestamp bounds cookie
    lifetime server-side to ``api_session_max_age``.

    Args:
        issued_at: epoch seconds; injectable for expiry tests. Defaults to now.
    """
    ts = int(time.time()) if issued_at is None else issued_at
    return f"{version}.{ts}.{_session_signature(version, ts, token)}"


_MAX_COOKIE_LEN = 1024


def decode_session_cookie(value: str | None) -> tuple[int, int, str] | None:
    """Parse ``{version}.{timestamp}.{hmac}`` without verifying anything.

    Returns ``(version, issued_at, hmac_hex)`` or ``None`` on malformed
    input. Legacy base64(JSON) cookies fail the numeric parse and force a
    re-login (acceptable: cookies expire in 12h). Cookie values longer than
    ``_MAX_COOKIE_LEN`` are rejected upfront to avoid attacker-controlled
    allocation amplification (security-reviewer M1).
    """
    if not value or len(value) > _MAX_COOKIE_LEN:
        return None
    parts = value.split(".")
    if len(parts) != 3:
        return None
    version_raw, ts_raw, mac = parts
    if not version_raw.isdigit() or not ts_raw.isdigit() or not mac:
        return None
    return int(version_raw), int(ts_raw), mac


def get_session_cookie_token(request: Request) -> str | None:
    """從 httpOnly session cookie 取出原始值（未解碼）。"""
    settings = get_settings()
    return request.cookies.get(settings.api_session_cookie_name)


def is_valid_session_cookie(cookie_value: str | None) -> bool:
    """Cookie 是否同時通過 HMAC、version 與有效期三重檢查。

    The HMAC is recomputed over the cookie's own (version, timestamp) with
    the **current** API token, so a tampered field, a stale token, or a
    forged signature all fail the ``compare_digest``. ``compare_digest`` is
    invoked **before** the version/expiry equality checks so the timing of a
    "valid signature, stale version" path matches a fully valid path,
    keeping the boolean short-circuits from leaking signature correctness
    via per-request timing (security-reviewer M3).
    """
    decoded = decode_session_cookie(cookie_value)
    if decoded is None:
        return False
    version, issued_at, mac = decoded
    expected = _session_signature(version, issued_at, current_api_token())
    mac_ok = secrets.compare_digest(mac, expected)
    version_ok = version == current_api_token_version()
    age = int(time.time()) - issued_at
    # Negative age = future-dated timestamp; reject (no clock-skew allowance
    # needed — issuer and verifier are the same server).
    age_ok = 0 <= age <= get_settings().api_session_max_age
    return mac_ok and version_ok and age_ok


def verify_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer_scheme),
) -> str:
    """驗證 Bearer Token 或 session cookie；不通過時 raise 401。"""
    bearer_token = credentials.credentials if credentials else None
    if bearer_token is not None and is_valid_api_token(bearer_token):
        return bearer_token
    cookie_value = get_session_cookie_token(request)
    if is_valid_session_cookie(cookie_value):
        return current_api_token()
    raise HTTPException(status_code=401, detail="Invalid token")


def validate_month(month: str) -> str:
    """驗證月份格式為 YYYY-MM。"""
    if not _MONTH_RE.match(month):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid month format: {month}. Expected YYYY-MM.",
        )
    return month


@dataclass(frozen=True)
class CommonMonthParams:
    """共用月份查詢參數。"""

    month: str


# FastAPI deduplicates get_db_session within a request; callers that also
# Depend(get_db_session) receive the same session instance.
async def get_month_params(
    month: str | None = Query(
        default=None,
        description="月份（YYYY-MM），預設為最近有資料的月份",
        pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
    ),
    session: AsyncSession = Depends(get_db_session),
) -> CommonMonthParams:
    """解析月份參數，未指定時自動取最近有帳單資料的月份。"""
    if month is not None:
        return CommonMonthParams(month=month)
    stmt = select(Bill.billing_month).order_by(Bill.billing_month.desc()).limit(1)
    result = await session.execute(stmt)
    latest = result.scalar_one_or_none()
    resolved = latest or date.today().strftime("%Y-%m")
    return CommonMonthParams(month=resolved)


class PaginationParams:
    """共用分頁查詢參數。"""

    def __init__(
        self,
        page: int = Query(default=1, ge=1, description="頁碼"),
        page_size: int = Query(default=20, ge=1, le=100, description="每頁筆數"),
    ):
        self.page = page
        self.page_size = page_size
        self.offset = (page - 1) * page_size


TokenDep = Depends(verify_token)
