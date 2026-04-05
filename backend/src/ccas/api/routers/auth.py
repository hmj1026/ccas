"""Browser session auth endpoints."""

import logging

from fastapi import APIRouter, HTTPException, Request, Response, status

from ccas.api.deps import get_session_cookie_token, is_valid_api_token
from ccas.api.schemas import ApiResponse, SessionLoginRequest, SessionStatus
from ccas.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _set_session_cookie(response: Response, token: str) -> None:
    """Set an HttpOnly session cookie on the response.

    Uses settings for cookie name, max-age, and secure flag.

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
        samesite="strict",
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
        samesite="strict",
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


@router.delete("/session", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(response: Response):
    """清除 browser session cookie。"""
    _clear_session_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
