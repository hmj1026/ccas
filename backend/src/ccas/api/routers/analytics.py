"""Analytics API：月趨勢、類別分布、銀行比較。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.api.deps import CommonMonthParams
from ccas.api.schemas import (
    ApiResponse,
    BankItem,
    CategoryItem,
    TrendItem,
)
from ccas.storage.database import get_db_session
from ccas.storage.models import Bill, Transaction
from ccas.storage.queries import fetch_bank_names

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/trend", response_model=ApiResponse[list[TrendItem]])
async def get_trend(
    months: int = Query(default=6, ge=1, le=24, description="回溯月數"),
    session: AsyncSession = Depends(get_db_session),
):
    """取得最近 N 個月的消費總額趨勢。"""
    from datetime import date

    today = date.today()
    # 產生最近 N 個月的月份清單
    month_list = []
    for i in range(months - 1, -1, -1):
        y = today.year
        m = today.month - i
        while m <= 0:
            m += 12
            y -= 1
        month_list.append(f"{y:04d}-{m:02d}")

    stmt = (
        select(Bill.billing_month, func.sum(Bill.total_amount))
        .where(Bill.billing_month.in_(month_list))
        .group_by(Bill.billing_month)
        .order_by(Bill.billing_month)
    )
    result = await session.execute(stmt)
    month_totals = {row[0]: row[1] for row in result.all()}

    data = [TrendItem(month=m, total=month_totals.get(m, 0)) for m in month_list]
    return ApiResponse(data=data)


@router.get("/categories", response_model=ApiResponse[list[CategoryItem]])
async def get_categories(
    params: CommonMonthParams = Depends(),
    session: AsyncSession = Depends(get_db_session),
):
    """取得指定月份的類別分布。"""
    stmt = (
        select(
            func.coalesce(Transaction.category, "未分類"),
            func.sum(Transaction.amount),
        )
        .join(Bill, Transaction.bill_id == Bill.id)
        .where(Bill.billing_month == params.month)
        .group_by(func.coalesce(Transaction.category, "未分類"))
        .order_by(func.sum(Transaction.amount).desc())
    )
    result = await session.execute(stmt)
    data = [CategoryItem(category=row[0], total=row[1]) for row in result.all()]
    return ApiResponse(data=data)


@router.get("/banks", response_model=ApiResponse[list[BankItem]])
async def get_banks(
    params: CommonMonthParams = Depends(),
    session: AsyncSession = Depends(get_db_session),
):
    """取得指定月份按銀行彙總的消費總額。"""
    bank_names = await fetch_bank_names(session)

    stmt = (
        select(Bill.bank_code, func.sum(Bill.total_amount))
        .where(Bill.billing_month == params.month)
        .group_by(Bill.bank_code)
        .order_by(func.sum(Bill.total_amount).desc())
    )
    result = await session.execute(stmt)
    data = [
        BankItem(
            bank_code=row[0],
            bank_name=bank_names.get(row[0]),
            total=row[1],
        )
        for row in result.all()
    ]
    return ApiResponse(data=data)
