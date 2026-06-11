"""ENABLE_API_DOCS 開關整合測試。

預設關閉（/docs、/redoc、/openapi.json 皆 404）；
設為 true 時開啟，且 docs 路徑跳過 CSP header。
"""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from ccas.api.app import create_app
from ccas.config import get_settings

_DOC_PATHS = ("/docs", "/redoc", "/openapi.json")


@pytest.fixture(autouse=True)
def _settings_cache():
    """Clear the lru_cache so each test rebuilds Settings from current env."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def _build_client() -> AsyncGenerator[AsyncClient, None]:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_docs_disabled_by_default(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("ENABLE_API_DOCS", raising=False)
    get_settings.cache_clear()

    async for client in _build_client():
        for path in _DOC_PATHS:
            response = await client.get(path)
            assert response.status_code == 404, path
            # docs 關閉時 CSP exemption 也應關閉
            assert "Content-Security-Policy" in response.headers, path


async def test_docs_enabled_via_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ENABLE_API_DOCS", "true")
    get_settings.cache_clear()

    async for client in _build_client():
        for path in _DOC_PATHS:
            response = await client.get(path)
            assert response.status_code == 200, path
            # docs 路徑使用 CDN JS + inline script，CSP 必須跳過
            assert "Content-Security-Policy" not in response.headers, path

        # 非 docs 路徑仍應套用 CSP
        response = await client.get("/health")
        assert "Content-Security-Policy" in response.headers
