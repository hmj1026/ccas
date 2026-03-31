"""API 共用依賴：認證、共用查詢參數。"""

import re

from fastapi import Depends, HTTPException, Query, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ccas.config import get_settings

_MONTH_RE = re.compile(r"^\d{4}-(?:0[1-9]|1[0-2])$")
_bearer_scheme = HTTPBearer()


def verify_token(
    credentials: HTTPAuthorizationCredentials = Security(_bearer_scheme),
) -> str:
    """驗證 Bearer Token，回傳 token 值。"""
    settings = get_settings()
    if credentials.credentials != settings.api_token:
        raise HTTPException(status_code=401, detail="Invalid token")
    return credentials.credentials


def validate_month(month: str) -> str:
    """驗證月份格式為 YYYY-MM。"""
    if not _MONTH_RE.match(month):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid month format: {month}. Expected YYYY-MM.",
        )
    return month


class CommonMonthParams:
    """共用月份查詢參數。"""

    def __init__(
        self,
        month: str | None = Query(
            default=None,
            description="月份（YYYY-MM），預設為當月",
            pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
        ),
    ):
        from datetime import date

        if month is None:
            self.month = date.today().strftime("%Y-%m")
        else:
            self.month = month


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
