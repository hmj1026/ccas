"""整合測試共用 Fixtures。

提供 in-memory SQLite DB Session 與 httpx AsyncClient，
測試結束時自動清理資料表與引擎。
"""

import os
from collections.abc import AsyncGenerator, Generator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ccas.storage.models import BankConfig, Base
from ccas.storage.queries import invalidate_bank_names_cache

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test")
# Must be an integer string: Settings._validate_telegram_chat_id rejects
# non-numeric values (P1 hardening).
os.environ.setdefault("TELEGRAM_CHAT_ID", "123456789")
os.environ.setdefault("API_TOKEN", "test-token")

TEST_TOKEN = "test-token"


@pytest.fixture(autouse=True)
def _reset_bank_names_cache() -> Generator[None, None, None]:
    """Each test seeds its own in-memory DB; the module-level bank name
    cache in ccas.storage.queries must not leak entries across tests."""
    invalidate_bank_names_cache()
    yield
    invalidate_bank_names_cache()


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """提供 in-memory SQLite 的 AsyncSession，測試後清除所有資料表。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """提供連接 FastAPI 測試應用程式的 httpx AsyncClient（含 DB 注入）。"""
    from ccas.api.app import create_app
    from ccas.storage.database import get_db_session

    app = create_app()

    async def _override_db():
        yield db_session

    app.dependency_overrides[get_db_session] = _override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def auth_headers(token: str = TEST_TOKEN) -> dict[str, str]:
    """產生 Bearer Token 認證 header。"""
    return {"Authorization": f"Bearer {token}"}


def make_ctbc_bank_config() -> BankConfig:
    """建立標準 CTBC 測試用 BankConfig。"""
    return BankConfig(bank_code="CTBC", bank_name="中國信託", gmail_filter="from:ctbc")
