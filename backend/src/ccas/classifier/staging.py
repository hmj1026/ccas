"""Classifier 流程的 staging 資料存取層。

提供查詢未分類交易、查詢全部交易，
以及更新交易分類欄位的函式。
只更新 category 欄位，不改寫原始交易資料。
"""

from collections.abc import Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.storage.models import Transaction


async def fetch_unclassified_transactions(
    session: AsyncSession,
) -> Sequence[Transaction]:
    """查詢所有 category 為 NULL 的交易。

    Args:
        session: 非同步 DB Session。

    Returns:
        尚未分類的 Transaction 記錄清單。
    """
    stmt = select(Transaction).where(Transaction.category.is_(None))
    result = await session.execute(stmt)
    return result.scalars().all()


async def fetch_all_transactions(
    session: AsyncSession,
) -> Sequence[Transaction]:
    """查詢所有交易（用於重跑分類）。

    Args:
        session: 非同步 DB Session。

    Returns:
        所有 Transaction 記錄清單。
    """
    stmt = select(Transaction)
    result = await session.execute(stmt)
    return result.scalars().all()


async def update_transaction_category(
    session: AsyncSession,
    transaction_id: int,
    category: str,
) -> None:
    """僅更新指定交易的 category 欄位。

    只修改 category，不改寫其他原始交易欄位
    （merchant、trans_date、amount 等）。

    Args:
        session: 非同步 DB Session。
        transaction_id: 交易 ID。
        category: 分類結果。
    """
    stmt = (
        update(Transaction)
        .where(Transaction.id == transaction_id)
        .values(category=category)
    )
    await session.execute(stmt)
