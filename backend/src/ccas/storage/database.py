"""資料庫連線與 Session 管理。

提供 SQLAlchemy 非同步引擎建立、Session Factory，
以及 FastAPI 依賴注入用的 DB Session Generator。
SQLite 連線時自動啟用 WAL mode 以提升並行讀取效能。
"""

from collections.abc import AsyncGenerator
from functools import lru_cache

from sqlalchemy import event
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import ConnectionPoolEntry

from ccas.config import get_settings


def _set_sqlite_wal(
    dbapi_connection: DBAPIConnection,
    connection_record: ConnectionPoolEntry,
) -> None:
    """設定 SQLite WAL mode、synchronous=NORMAL 與 busy_timeout=30s。

    作為 SQLAlchemy ``connect`` 事件監聽器，在每次建立新的
    DBAPI 連線時自動執行 PRAGMA 設定。

    ``busy_timeout=30000`` (issue #6): aiosqlite 預設 5 s 對長時間
    pipeline run 不夠 — worker、scheduler heartbeat、backend GET 共用
    ``data/ccas.db``，``stage_finished`` 的 read-modify-write 會在
    rolling 廣播 ingest 時撞 ``database is locked``。30 s 等待窗口涵蓋
    scheduler 30 s heartbeat 週期，且大幅超過正常 commit 延遲。
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    """建立 SQLAlchemy 非同步引擎（singleton）。

    從 Settings 讀取 database_url，並註冊 WAL mode 事件監聯器。
    結果快取，避免每次 request 重建引擎與連線池。
    """
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    event.listen(engine.sync_engine, "connect", _set_sqlite_wal)
    return engine


@lru_cache(maxsize=1)
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """建立非同步 Session Factory（singleton）。

    Returns:
        設定好的 async_sessionmaker 實例。
    """
    engine = get_engine()
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依賴注入用的 DB Session Generator。

    Yields:
        AsyncSession 實例，函式結束時自動關閉。
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        yield session
