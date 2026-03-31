"""FastAPI 應用程式工廠。

提供 ``create_app()`` 建立 CCAS API 實例，
包含健康檢查端點及業務 API 路由（含 Bearer Token 認證）。
"""

from fastapi import Depends, FastAPI

from ccas.api.deps import verify_token
from ccas.api.routers import analytics, bills, overview, pipeline, settings, transactions


def create_app() -> FastAPI:
    """建立並回傳 FastAPI 應用程式實例。

    ``/health`` 不需認證；所有 ``/api`` 路由皆需 Bearer Token。
    """
    app = FastAPI(title="CCAS", version="0.1.0")

    @app.get("/health")
    async def health():
        """健康檢查端點，回傳 ``{"status": "ok"}``。"""
        return {"status": "ok"}

    # 所有業務 API 路由，統一加上 Bearer Token 認證
    api_dependencies = [Depends(verify_token)]
    app.include_router(overview.router, dependencies=api_dependencies)
    app.include_router(transactions.router, dependencies=api_dependencies)
    app.include_router(analytics.router, dependencies=api_dependencies)
    app.include_router(bills.router, dependencies=api_dependencies)
    app.include_router(settings.router, dependencies=api_dependencies)
    app.include_router(pipeline.router, dependencies=api_dependencies)

    return app
