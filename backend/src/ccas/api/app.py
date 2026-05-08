"""FastAPI 應用程式工廠。

提供 ``create_app()`` 建立 CCAS API 實例，
包含健康檢查端點及業務 API 路由（含 Bearer Token 認證）。
"""

from fastapi import Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from ccas.api.deps import verify_token
from ccas.api.routers import (
    analytics,
    auth,
    bills,
    overview,
    pipeline,
    rules,
    settings,
    staged_attachments,
    transactions,
)
from ccas.api.routers.setup import admin as setup_admin
from ccas.api.routers.setup import banks as setup_banks
from ccas.api.routers.setup import gmail as setup_gmail
from ccas.api.routers.setup import secrets as setup_secrets
from ccas.config import get_settings

# Same CSP policy as nginx.conf（defense in depth；修改時請同步兩處）。
_CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "font-src 'self' data:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)

# Swagger UI / ReDoc / OpenAPI schema 這些路徑使用外部 CDN JS + inline
# script，套 CSP 會整個壞掉；直接跳過。正式流量走 nginx 不會打到這些端點，
# 只在開發或內部除錯時使用。
_CSP_EXEMPT_PATHS = frozenset({"/docs", "/redoc", "/openapi.json"})


class _SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if request.url.path not in _CSP_EXEMPT_PATHS:
            response.headers["Content-Security-Policy"] = _CONTENT_SECURITY_POLICY
        return response


def create_app() -> FastAPI:
    """建立並回傳 FastAPI 應用程式實例。

    ``/health`` 不需認證；所有 ``/api`` 路由皆需 Bearer Token。
    """
    settings_obj = get_settings()
    app = FastAPI(title="CCAS", version="0.1.0")
    app.add_middleware(_SecurityHeadersMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings_obj.get_frontend_origins(),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.get("/health")
    async def health():
        """健康檢查端點，回傳 ``{"status": "ok"}``。"""
        return {"status": "ok"}

    app.include_router(auth.router)

    # 所有業務 API 路由，統一加上 Bearer Token 認證
    api_dependencies = [Depends(verify_token)]
    app.include_router(overview.router, dependencies=api_dependencies)
    app.include_router(transactions.router, dependencies=api_dependencies)
    app.include_router(analytics.router, dependencies=api_dependencies)
    app.include_router(bills.router, dependencies=api_dependencies)
    app.include_router(settings.router, dependencies=api_dependencies)
    app.include_router(pipeline.router, dependencies=api_dependencies)
    app.include_router(rules.router, dependencies=api_dependencies)
    app.include_router(staged_attachments.router, dependencies=api_dependencies)
    # Setup UX routers（oauth-onboarding-ui）— 共用 verify_token 保護。
    app.include_router(setup_gmail.router, dependencies=api_dependencies)
    app.include_router(setup_banks.router, dependencies=api_dependencies)
    app.include_router(setup_secrets.router, dependencies=api_dependencies)
    app.include_router(setup_admin.router, dependencies=api_dependencies)

    return app
