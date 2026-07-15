"""staging 資料存取層的單元測試。

測試 fetch_unclassified_transactions / fetch_all_transactions /
update_transaction_category 三個函式。使用 in-memory SQLite + 真實 ORM
model，讓 SQL 實際執行（不 mock session）。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ccas.classifier.staging import (
    fetch_all_transactions,
    fetch_unclassified_transactions,
    update_transaction_category,
)
from ccas.storage.models import Base, Transaction


@pytest.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


async def _add_transaction(
    session: AsyncSession,
    *,
    merchant: str,
    amount: int = 100,
    category: str | None = None,
) -> Transaction:
    txn = Transaction(
        bill_id=1,
        trans_date=date(2026, 1, 1),
        merchant=merchant,
        amount=amount,
        category=category,
    )
    session.add(txn)
    await session.commit()
    return txn


class TestFetchUnclassifiedTransactions:
    async def test_returns_only_null_category_rows(self, session: AsyncSession) -> None:
        await _add_transaction(session, merchant="星巴克", category=None)
        await _add_transaction(session, merchant="家樂福", category="購物")

        rows = await fetch_unclassified_transactions(session)

        assert len(rows) == 1
        assert rows[0].merchant == "星巴克"
        assert rows[0].category is None

    async def test_empty_when_all_classified(self, session: AsyncSession) -> None:
        await _add_transaction(session, merchant="家樂福", category="購物")

        rows = await fetch_unclassified_transactions(session)

        assert list(rows) == []

    async def test_empty_table(self, session: AsyncSession) -> None:
        rows = await fetch_unclassified_transactions(session)
        assert list(rows) == []


class TestFetchAllTransactions:
    async def test_returns_every_row(self, session: AsyncSession) -> None:
        await _add_transaction(session, merchant="星巴克", category=None)
        await _add_transaction(session, merchant="家樂福", category="購物")

        rows = await fetch_all_transactions(session)

        merchants = {r.merchant for r in rows}
        assert merchants == {"星巴克", "家樂福"}

    async def test_empty_table(self, session: AsyncSession) -> None:
        rows = await fetch_all_transactions(session)
        assert list(rows) == []


class TestUpdateTransactionCategory:
    async def test_sets_category(self, session: AsyncSession) -> None:
        txn = await _add_transaction(session, merchant="星巴克", category=None)

        await update_transaction_category(session, txn.id, "餐飲")

        # 直接讀欄位值，繞過 identity-map 取得 DB 端最新值。
        result = await session.execute(
            select(Transaction.category).where(Transaction.id == txn.id)
        )
        assert result.scalar_one() == "餐飲"

    async def test_only_updates_category_not_other_fields(
        self, session: AsyncSession
    ) -> None:
        txn = await _add_transaction(
            session, merchant="星巴克", amount=250, category=None
        )

        await update_transaction_category(session, txn.id, "餐飲")

        row = (
            await session.execute(
                select(
                    Transaction.merchant,
                    Transaction.amount,
                    Transaction.category,
                ).where(Transaction.id == txn.id)
            )
        ).one()
        assert row.merchant == "星巴克"
        assert row.amount == 250
        assert row.category == "餐飲"

    async def test_does_not_touch_other_rows(self, session: AsyncSession) -> None:
        target = await _add_transaction(session, merchant="星巴克", category=None)
        other = await _add_transaction(session, merchant="家樂福", category=None)

        await update_transaction_category(session, target.id, "餐飲")

        other_category = (
            await session.execute(
                select(Transaction.category).where(Transaction.id == other.id)
            )
        ).scalar_one()
        assert other_category is None

    async def test_missing_id_is_noop(self, session: AsyncSession) -> None:
        # 不存在的 id 不應拋例外（UPDATE 影響 0 列）。
        await update_transaction_category(session, 999999, "餐飲")

        rows = await fetch_all_transactions(session)
        assert list(rows) == []
