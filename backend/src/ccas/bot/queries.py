"""Bot 查詢用資料存取層。

提供帳單、交易的查詢函式，供指令 handler 使用。
所有函式皆為純查詢，不修改資料。
"""

from collections.abc import Sequence
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ccas.storage.models import BankConfig, Bill, Transaction


async def fetch_bills_by_month(
    session: AsyncSession,
    billing_month: str,
    *,
    paid_filter: str = "all",
) -> Sequence[Bill]:
    """查詢指定月份帳單，可依繳費狀態篩選。

    Args:
        session: 非同步 DB Session。
        billing_month: 帳單月份（YYYY-MM）。
        paid_filter: ``"all"`` / ``"unpaid"`` / ``"paid"``。

    Returns:
        符合條件的 Bill 清單（含 eager-loaded transactions）。
    """
    stmt = (
        select(Bill)
        .options(selectinload(Bill.transactions))
        .where(Bill.billing_month == billing_month)
        .order_by(Bill.bank_code)
    )
    if paid_filter == "unpaid":
        stmt = stmt.where(Bill.is_paid.is_(False))
    elif paid_filter == "paid":
        stmt = stmt.where(Bill.is_paid.is_(True))
    result = await session.execute(stmt)
    return result.scalars().all()


async def fetch_upcoming_bills(
    session: AsyncSession,
    *,
    today: date | None = None,
    days: int = 7,
) -> Sequence[Bill]:
    """查詢未來 N 天內到期且未繳的帳單。

    Args:
        session: 非同步 DB Session。
        today: 基準日（預設為今天）。
        days: 往後查詢天數（預設 7 天）。

    Returns:
        即將到期的未繳 Bill 清單。
    """
    if today is None:
        today = date.today()
    deadline = today + timedelta(days=days)
    stmt = (
        select(Bill)
        .where(
            Bill.is_paid.is_(False),
            Bill.due_date >= today,
            Bill.due_date <= deadline,
        )
        .order_by(Bill.due_date, Bill.bank_code)
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def fetch_bill_by_id(
    session: AsyncSession,
    bill_id: int,
) -> Bill | None:
    """依 ID 查詢單一帳單。

    Args:
        session: 非同步 DB Session。
        bill_id: 帳單 ID。

    Returns:
        Bill 或 None（找不到時）。
    """
    stmt = select(Bill).where(Bill.id == bill_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def fetch_category_summary(
    session: AsyncSession,
    billing_month: str,
) -> Sequence[tuple[str, int]]:
    """查詢指定月份依分類彙總的消費金額。

    Args:
        session: 非同步 DB Session。
        billing_month: 帳單月份（YYYY-MM）。

    Returns:
        ``(category, total_amount)`` tuple 清單，依金額降冪排列。
    """
    stmt = (
        select(
            func.coalesce(Transaction.category, "未分類"),
            func.sum(Transaction.amount),
        )
        .join(Bill, Transaction.bill_id == Bill.id)
        .where(Bill.billing_month == billing_month)
        .group_by(func.coalesce(Transaction.category, "未分類"))
        .order_by(func.sum(Transaction.amount).desc())
    )
    result = await session.execute(stmt)
    return result.all()  # type: ignore[return-value]


async def fetch_bank_names(
    session: AsyncSession,
) -> dict[str, str]:
    """查詢所有銀行代碼與名稱的對照。

    Returns:
        ``{bank_code: bank_name}`` dict。
    """
    stmt = select(BankConfig.bank_code, BankConfig.bank_name)
    result = await session.execute(stmt)
    return {row[0]: row[1] for row in result.all()}
