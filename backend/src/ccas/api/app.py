"""FastAPI 應用程式工廠。

提供 ``create_app()`` 建立 CCAS API 實例，
包含健康檢查端點及業務 API 路由（含 Bearer Token 認證）。
"""

import logging
from collections.abc import Awaitable
from typing import cast

from fastapi import Depends, FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis.asyncio import Redis as AsyncRedis
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from ccas.api.deps import verify_token
from ccas.api.routers import (
    analytics,
    analytics_v2,
    auth,
    bills,
    budgets,
    exports,
    overview,
    pipeline,
    reminders_settings,
    rules,
    settings,
    staged_attachments,
    transactions,
    transactions_edit,
)
from ccas.api.routers.setup import admin as setup_admin
from ccas.api.routers.setup import banks as setup_banks
from ccas.api.routers.setup import gmail as setup_gmail
from ccas.api.routers.setup import secrets as setup_secrets
from ccas.config import get_settings
from ccas.storage.database import get_db_session

logger = logging.getLogger(__name__)

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
# script，套 CSP 會整個壞掉；docs 啟用時（ENABLE_API_DOCS=true）直接跳過。
# 正式流量走 nginx 不會打到這些端點，只在開發或內部除錯時使用。
_CSP_EXEMPT_PATHS = frozenset({"/docs", "/redoc", "/openapi.json"})


class _SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, docs_enabled: bool = False) -> None:  # type: ignore[no-untyped-def]
        super().__init__(app)
        self._docs_enabled = docs_enabled

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if not (self._docs_enabled and request.url.path in _CSP_EXEMPT_PATHS):
            response.headers["Content-Security-Policy"] = _CONTENT_SECURITY_POLICY
        return response


def create_app() -> FastAPI:
    """建立並回傳 FastAPI 應用程式實例。

    ``/health`` 不需認證；所有 ``/api`` 路由皆需 Bearer Token。
    """
    settings_obj = get_settings()
    docs_enabled = settings_obj.enable_api_docs
    app = FastAPI(
        title="CCAS",
        version="0.1.0",
        # API docs are opt-in（ENABLE_API_DOCS=true）；production 預設關閉，
        # 避免暴露完整 API surface 給未認證流量。
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )
    app.add_middleware(_SecurityHeadersMiddleware, docs_enabled=docs_enabled)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings_obj.get_frontend_origins(),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        # Pagination total for list endpoints (e.g. GET /api/pipeline/runs);
        # browsers cannot read it cross-origin unless explicitly exposed.
        expose_headers=["X-Total-Count"],
    )

    @app.exception_handler(RequestValidationError)
    async def _validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """422 驗證錯誤改用專案統一信封格式。

        一般 ``HTTPException`` 由下方 ``_http_exception_handler`` 處理（兩者註冊
        不同例外型別，互不覆蓋）。
        """
        message = "; ".join(
            "{loc} -> {msg}".format(
                loc=".".join(str(part) for part in err.get("loc", ())),
                msg=err.get("msg", ""),
            )
            for err in exc.errors()
        )
        return JSONResponse(
            status_code=422,
            content={"success": False, "message": message, "data": None},
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        """HTTPException 統一改用專案信封格式 ``{success, message, data}``。

        涵蓋業務路由拋出的 ``fastapi.HTTPException``（401/403/404/409/413/422…）
        以及 Starlette 路由層錯誤（如未匹配路由的 404）。原 ``status_code`` 與既有
        ``headers``（如 401 的 ``WWW-Authenticate``）皆完整保留。

        422 ``RequestValidationError`` 不在此處理（已由上方專用 handler 攔截，
        且兩者註冊的是不同例外型別，互不覆蓋）。
        """
        return JSONResponse(
            status_code=exc.status_code,
            content={"success": False, "message": str(exc.detail), "data": None},
            headers=exc.headers,
        )

    @app.get("/health")
    @app.get("/api/health")
    async def health():
        """健康檢查端點，回傳 ``{"status": "ok"}``。

        Both ``/health`` (proxy & internal docker healthcheck) and ``/api/health``
        (reverse-proxy passthrough from ``proxy:/api/*`` location block) are
        registered so external callers behind nginx see a 200 without nginx
        having to strip the ``/api/`` prefix (which would break ``/api/setup/*``
        and ``/api/bills``). See compose-pull-deploy §1.11.
        """
        return {"status": "ok"}

    @app.get("/health/ready")
    async def health_ready(
        session: AsyncSession = Depends(get_db_session),
    ) -> JSONResponse:
        """Readiness probe：實際探測 DB 與 Redis 連線。

        ``/health`` 維持純 liveness（process 起來即 200）；本端點供
        docker healthcheck / 部署驗證使用，任一依賴失敗回 503。
        """
        db_ok = True
        try:
            await session.execute(text("SELECT 1"))
        except (SQLAlchemyError, OSError):
            logger.exception("Readiness probe: database check failed")
            db_ok = False

        redis_ok = True
        redis_client = AsyncRedis.from_url(settings_obj.redis_url)
        try:
            # redis-py types ping() as ResponseT (Awaitable | raw) — narrow it
            # for the async client.
            await cast("Awaitable[object]", redis_client.ping())
        except (RedisError, OSError):
            logger.exception("Readiness probe: redis check failed")
            redis_ok = False
        finally:
            await redis_client.aclose()

        ready = db_ok and redis_ok
        return JSONResponse(
            status_code=200 if ready else 503,
            content={
                "status": "ok" if ready else "degraded",
                "db": "ok" if db_ok else "error",
                "redis": "ok" if redis_ok else "error",
            },
        )

    app.include_router(auth.router)

    # 所有業務 API 路由，統一加上 Bearer Token 認證
    api_dependencies = [Depends(verify_token)]
    app.include_router(overview.router, dependencies=api_dependencies)
    app.include_router(transactions.router, dependencies=api_dependencies)
    # Register exports BEFORE transactions_edit so the static /transactions/export
    # path resolves before the {transaction_id} dynamic segment in transactions_edit.
    app.include_router(exports.router, dependencies=api_dependencies)
    app.include_router(transactions_edit.router, dependencies=api_dependencies)
    app.include_router(analytics.router, dependencies=api_dependencies)
    app.include_router(analytics_v2.router, dependencies=api_dependencies)
    app.include_router(bills.router, dependencies=api_dependencies)
    app.include_router(settings.router, dependencies=api_dependencies)
    app.include_router(pipeline.router, dependencies=api_dependencies)
    app.include_router(rules.router, dependencies=api_dependencies)
    app.include_router(reminders_settings.router, dependencies=api_dependencies)
    app.include_router(budgets.router, dependencies=api_dependencies)
    app.include_router(staged_attachments.router, dependencies=api_dependencies)
    # Setup UX routers（oauth-onboarding-ui）— 共用 verify_token 保護。
    app.include_router(setup_gmail.router, dependencies=api_dependencies)
    app.include_router(setup_banks.router, dependencies=api_dependencies)
    app.include_router(setup_secrets.router, dependencies=api_dependencies)
    app.include_router(setup_admin.router, dependencies=api_dependencies)

    return app
