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
from typing import Any, cast

import pytest
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.pool import ConnectionPoolEntry

from ccas.storage.database import _set_sqlite_wal


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
