"""API 共用依賴：認證、共用查詢參數。"""

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

_MONTH_RE = re.compile(r"^\d{4}-(?:0[1-9]|1[0-2])$")
_bearer_scheme = HTTPBearer(auto_error=False)


def is_valid_api_token(token: str | None) -> bool:
    """檢查 token 是否與設定值相符。"""
    if not token:
        return False
    return secrets.compare_digest(token, get_settings().api_token)


def get_session_cookie_token(request: Request) -> str | None:
    """從 httpOnly session cookie 讀取 token。"""
    settings = get_settings()
    return request.cookies.get(settings.api_session_cookie_name)


def verify_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer_scheme),
) -> str:
    """驗證 Bearer Token，回傳 token 值。"""
    bearer_token = credentials.credentials if credentials else None
    cookie_token = get_session_cookie_token(request)
    if is_valid_api_token(bearer_token):
        return bearer_token  # type: ignore[return-value]
    if is_valid_api_token(cookie_token):
        return cookie_token  # type: ignore[return-value]
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
