"""SQLite engine PRAGMA setup tests (issue #6).

Verifies that every newly opened DBAPI connection is configured with:

- ``journal_mode=WAL`` — enables concurrent readers + single writer.
- ``synchronous=NORMAL`` — drops fsync per commit; safe with WAL.
- ``busy_timeout=30000`` — waits 30 s on lock contention before raising
  ``sqlite3.OperationalError``. Without this, aiosqlite defaults to ~5 s
  which is too short for long pipeline runs where the worker, the scheduler
  heartbeat, and backend GET requests all share ``data/ccas.db``.

Issue #6: pipeline runs hit ``database is locked`` during ``stage_finished``
when the worker is doing read-modify-write of ``stage_summary`` JSON while
the scheduler heartbeat job is also writing.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from types import SimpleNamespace
from typing import Any, cast

import pytest
from sqlalchemy import event, text
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import ConnectionPoolEntry

from ccas.storage import database as database_module
from ccas.storage.database import (
    _set_sqlite_wal,
    get_db_session,
    get_engine,
    get_session_factory,
)


def _apply(conn: sqlite3.Connection) -> None:
    """Invoke ``_set_sqlite_wal`` on a stdlib ``sqlite3.Connection``.

    SQLAlchemy types the listener as ``DBAPIConnection`` /
    ``ConnectionPoolEntry``; the runtime values it receives are the same
    underlying ``sqlite3.Connection``. Cast at the call site so pyright is
    happy without polluting the signature.
    """
    _set_sqlite_wal(
        cast(DBAPIConnection, conn),
        cast(ConnectionPoolEntry, cast(Any, None)),
    )


@pytest.fixture
def in_memory_connection() -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(":memory:")
    yield conn
    conn.close()


def test_set_sqlite_wal_enables_journal_mode_wal(
    in_memory_connection: sqlite3.Connection,
) -> None:
    _apply(in_memory_connection)

    cursor = in_memory_connection.cursor()
    # In-memory DBs can't actually enter WAL mode (returns "memory"), but the
    # PRAGMA call must succeed and return a non-error value. Real on-disk
    # connections in production return "wal".
    mode = cursor.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode in {"wal", "memory"}


def test_set_sqlite_wal_sets_synchronous_normal(
    in_memory_connection: sqlite3.Connection,
) -> None:
    _apply(in_memory_connection)

    cursor = in_memory_connection.cursor()
    # synchronous=NORMAL == 1
    sync = cursor.execute("PRAGMA synchronous").fetchone()[0]
    assert sync == 1


def test_set_sqlite_wal_sets_busy_timeout_30_seconds(
    in_memory_connection: sqlite3.Connection,
) -> None:
    """Issue #6 guard: busy_timeout must be 30 s so concurrent writers wait
    instead of immediately raising ``database is locked`` during long runs."""
    _apply(in_memory_connection)

    cursor = in_memory_connection.cursor()
    timeout_ms = cursor.execute("PRAGMA busy_timeout").fetchone()[0]
    assert timeout_ms == 30_000, (
        "busy_timeout must be 30000 ms; SQLite default of 0 lets aiosqlite "
        "raise database-is-locked after ~5 s, which is too short for long "
        "pipeline runs (issue #6)"
    )


@pytest.fixture
def _memory_engine(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Point engine/session factories at a throwaway in-memory SQLite URL.

    ``get_engine`` / ``get_session_factory`` are ``lru_cache`` singletons that
    read ``database_url`` from ``get_settings()``. Patch the module-level
    ``get_settings`` to a stub returning an in-memory URL and clear the caches
    on entry and exit so these tests never build (or leak) the production
    engine bound to the real ``data/ccas.db``.
    """
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    monkeypatch.setattr(
        database_module,
        "get_settings",
        lambda: SimpleNamespace(database_url="sqlite+aiosqlite://"),
    )
    yield
    get_engine.cache_clear()
    get_session_factory.cache_clear()


def test_get_engine_builds_cached_async_engine_with_wal_listener(
    _memory_engine: None,
) -> None:
    engine = get_engine()

    assert isinstance(engine, AsyncEngine)
    # The connect listener that applies the WAL/foreign-key PRAGMAs must be
    # registered on the underlying sync engine.
    assert event.contains(engine.sync_engine, "connect", _set_sqlite_wal)
    # lru_cache(maxsize=1) → same instance on every call (singleton).
    assert get_engine() is engine


def test_get_session_factory_is_cached_and_bound_to_engine(
    _memory_engine: None,
) -> None:
    factory = get_session_factory()

    assert isinstance(factory, async_sessionmaker)
    # Built on top of the cached engine and itself cached as a singleton.
    assert factory.kw["bind"] is get_engine()
    assert get_session_factory() is factory


async def test_get_db_session_yields_usable_async_session(
    _memory_engine: None,
) -> None:
    agen = get_db_session()
    session = await anext(agen)
    try:
        assert isinstance(session, AsyncSession)
        # A live query proves the session is fully wired to the engine and the
        # connect listener fired without raising.
        result = await session.execute(text("SELECT 1"))
        assert result.scalar_one() == 1
    finally:
        # Exhaust the generator so its ``async with`` block closes the session.
        with pytest.raises(StopAsyncIteration):
            await anext(agen)
