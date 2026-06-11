"""Model-declared index tests (db-missing-indexes).

Verifies that the hot-path indexes added in alembic ``ec74b5138c9f`` are
mirrored in the ORM models' ``__table_args__`` (SSOT consistency), and that
the two partial indexes on ``bills`` carry their ``WHERE`` predicate when
materialized on SQLite.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from ccas.storage.models import Base

EXPECTED_INDEXES: dict[str, str] = {
    "ix_transactions_bill_id": "transactions",
    "ix_payment_reminders_bill_id": "payment_reminders",
    "ix_staged_attachments_status": "staged_attachments",
    "ix_bills_billing_month": "bills",
    "ix_bills_is_notified_false": "bills",
    "ix_bills_is_paid_false": "bills",
}


@pytest.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


async def _fetch_index_rows(engine: AsyncEngine) -> dict[str, tuple[str, str | None]]:
    """Return {index_name: (table_name, create_sql)} from sqlite_master."""
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT name, tbl_name, sql FROM sqlite_master "
                "WHERE type = 'index' AND name LIKE 'ix_%'"
            )
        )
        return {name: (tbl, sql) for name, tbl, sql in result.fetchall()}


async def test_models_declare_missing_indexes(engine: AsyncEngine) -> None:
    rows = await _fetch_index_rows(engine)

    for index_name, table_name in EXPECTED_INDEXES.items():
        assert index_name in rows, f"index {index_name} not created by metadata"
        assert rows[index_name][0] == table_name


async def test_bills_partial_indexes_have_where_clause(engine: AsyncEngine) -> None:
    rows = await _fetch_index_rows(engine)

    notified_sql = rows["ix_bills_is_notified_false"][1]
    paid_sql = rows["ix_bills_is_paid_false"][1]
    assert notified_sql is not None and "is_notified = 0" in notified_sql
    assert paid_sql is not None and "is_paid = 0" in paid_sql
