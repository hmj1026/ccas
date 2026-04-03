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
    settings,
    transactions,
)
from ccas.config import get_settings


class _SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
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

    return app
