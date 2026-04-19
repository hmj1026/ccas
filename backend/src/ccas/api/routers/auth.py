"""Browser session auth endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from ccas.api.deps import get_session_cookie_token, is_valid_api_token, verify_token
from ccas.api.schemas import ApiResponse, SessionLoginRequest, SessionStatus
from ccas.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _set_session_cookie(response: Response, token: str) -> None:
    """Set an HttpOnly session cookie on the response.

    Uses settings for cookie name, max-age, and secure flag.

    SameSite=Lax is used (not Strict) because Chrome's stricter Strict
    enforcement on the ``localhost`` host drops the cookie on the initial
    client-side navigation after login, leaving the SPA stuck on /login.
    Lax is CSRF-safe here: all state-changing endpoints are POST/PATCH/DELETE
    (which browsers never send cross-site with Lax cookies), and CORS
    ``allow_headers`` restricts custom Authorization headers so cookie-as-
    bearer cannot be replayed cross-origin.

    Args:
        response: FastAPI Response to attach the cookie to.
        token: The API token value to store in the cookie.
    """
    settings = get_settings()
    response.set_cookie(
        key=settings.api_session_cookie_name,
        value=token,
        max_age=settings.api_session_max_age,
        httponly=True,
        samesite="lax",
        secure=settings.api_cookie_secure,
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    """Delete the session cookie from the response.

    Uses the same cookie attributes (name, secure, samesite) as _set_session_cookie
    to ensure the browser removes the existing cookie.

    Args:
        response: FastAPI Response to clear the cookie on.
    """
    settings = get_settings()
    response.delete_cookie(
        key=settings.api_session_cookie_name,
        httponly=True,
        samesite="lax",
        secure=settings.api_cookie_secure,
        path="/",
    )


@router.get("/session", response_model=ApiResponse[SessionStatus])
async def get_session_status(request: Request):
    """回傳目前瀏覽器是否已具備有效 session。"""
    cookie_token = get_session_cookie_token(request)
    data = SessionStatus(authenticated=is_valid_api_token(cookie_token))
    return ApiResponse(data=data)


@router.post("/session", status_code=status.HTTP_204_NO_CONTENT)
async def create_session(
    request: Request, body: SessionLoginRequest, response: Response
):
    """以 API token 建立 browser session cookie。"""
    remote_addr = request.client.host if request.client else "unknown"
    if not is_valid_api_token(body.token):
        logger.warning("auth_failed: remote_addr=%s", remote_addr)
        raise HTTPException(status_code=401, detail="Invalid token")
    logger.info("session_created: remote_addr=%s", remote_addr)
    _set_session_cookie(response, body.token)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.delete(
    "/session",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(verify_token)],
)
async def delete_session(response: Response):
    """清除 browser session cookie。

    需通過 ``verify_token``：要求請求帶有效 Bearer token 或 session cookie
    才能執行登出，避免未認證請求無謂地觸碰 auth endpoint（減少 auth
    surface）。SameSite=Lax 下 cross-site top-level navigation 無法發出
    DELETE，所以無實際 CSRF 風險，但此檢查為 defense in depth。
    """
    _clear_session_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
