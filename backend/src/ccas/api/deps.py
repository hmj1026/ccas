"""API 共用依賴：認證、共用查詢參數。"""

import base64
import json
import logging
import re
import secrets
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
    return settings.api_token


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


def encode_session_cookie(token: str, version: int) -> str:
    """Pack (token, version) into a single opaque cookie value.

    Format: urlsafe base64 of JSON ``{"t": <token>, "v": <int>}``. The cookie
    is HttpOnly so the client never inspects it; the encoding only serves to
    pin the cookie to a token version that the server can later validate.
    """
    payload = json.dumps({"t": token, "v": version}, separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")


_MAX_COOKIE_LEN = 1024


def decode_session_cookie(value: str | None) -> tuple[str, int] | None:
    """Reverse of ``encode_session_cookie``; returns ``None`` on any failure.

    Legacy cookies issued before this scheme are plain token strings and will
    fail to decode, forcing a re-login (acceptable: cookies expire in 12h).
    Cookie values longer than ``_MAX_COOKIE_LEN`` are rejected upfront to
    avoid attacker-controlled allocation amplification through base64+JSON
    decoding (security-reviewer M1).
    """
    if not value or len(value) > _MAX_COOKIE_LEN:
        return None
    try:
        raw = base64.urlsafe_b64decode(value.encode("ascii"))
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    token = data.get("t")
    version = data.get("v")
    if not isinstance(token, str) or not isinstance(version, int):
        return None
    return token, version


def get_session_cookie_token(request: Request) -> str | None:
    """從 httpOnly session cookie 取出原始值（未解碼）。"""
    settings = get_settings()
    return request.cookies.get(settings.api_session_cookie_name)


def is_valid_session_cookie(cookie_value: str | None) -> bool:
    """Cookie 是否同時通過 token 比對與 version 比對。

    ``compare_digest`` is invoked **before** the version equality check so the
    timing of a "valid token, stale version" path matches a "valid token,
    valid version" path. This keeps an attacker who can observe per-request
    timing from learning whether their guess of the token is correct via the
    integer version comparison short-circuit (security-reviewer M3).
    """
    decoded = decode_session_cookie(cookie_value)
    if decoded is None:
        return False
    cookie_token, cookie_version = decoded
    token_ok = secrets.compare_digest(cookie_token, current_api_token())
    version_ok = cookie_version == current_api_token_version()
    return token_ok and version_ok


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
