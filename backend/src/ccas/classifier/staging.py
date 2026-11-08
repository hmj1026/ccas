"""Classifier 流程的 staging 資料存取層。

提供查詢未分類交易與查詢全部交易的函式（分類寫入由 ``job`` 批次處理）。
"""

from collections.abc import Sequence

from sqlalchemy import select
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
