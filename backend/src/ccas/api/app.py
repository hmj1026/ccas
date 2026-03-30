"""FastAPI 應用程式工廠。

提供 ``create_app()`` 建立 CCAS API 實例，
包含健康檢查端點及後續路由掛載。
"""

from fastapi import FastAPI


def create_app() -> FastAPI:
    """建立並回傳 FastAPI 應用程式實例。

    設定基本 metadata，並註冊 ``/health`` 健康檢查端點。
    """
    app = FastAPI(title="CCAS", version="0.1.0")

    @app.get("/health")
    async def health():
        """健康檢查端點，回傳 ``{"status": "ok"}``。"""
        return {"status": "ok"}

    return app
