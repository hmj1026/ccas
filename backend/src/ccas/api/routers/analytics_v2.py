"""Insights v2 API（bills-management-and-insights §7）。

擴充既有 ``analytics.py`` 路由為 dashboard v2 提供：

- ``GET /api/analytics/compare/banks?year=&month=``：銀行對比
- ``GET /api/analytics/compare/years?metric=total|count``：年度對比
- ``GET /api/analytics/top-merchants?limit=&period=year|month|all``：商家排行

``categories`` 的 ``?compare_with_previous=true`` 擴充直接修改既有
``analytics.py`` 中的 endpoint（保持 backward compatibility）。
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.api.schemas import (
    ApiResponse,
    BankCompareItem,
    TopMerchantItem,
    TopMerchantPeriodLiteral,
    YearCompareItem,
    YearMetricLiteral,
)
from ccas.storage.database import get_db_session
from ccas.storage.models import Bill, Transaction
from ccas.storage.queries import fetch_bank_names

router = APIRouter(prefix="/api/analytics", tags=["analytics-v2"])


@router.get(
    "/compare/banks",
    response_model=ApiResponse[list[BankCompareItem]],
)
async def compare_banks(
    month: str | None = Query(
        default=None,
        description="月份（YYYY-MM）",
        pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
    ),
    year: int | None = Query(default=None, ge=2000, le=2099),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[list[BankCompareItem]]:
    """GROUP BY bank_code 回每銀行交易金額（DESC）。"""
    bank_names = await fetch_bank_names(session)

    stmt = (
        select(Bill.bank_code, func.coalesce(func.sum(Transaction.amount), 0))
        .join(Transaction, Transaction.bill_id == Bill.id)
        .group_by(Bill.bank_code)
        .order_by(func.sum(Transaction.amount).desc())
    )
    if month is not None:
        stmt = stmt.where(Bill.billing_month == month)
    elif year is not None:
        stmt = stmt.where(Bill.billing_month.startswith(f"{year}-"))

    rows = (await session.execute(stmt)).all()
    items = [
        BankCompareItem(
            bank_code=row[0],
            bank_name=bank_names.get(row[0]),
            total=int(row[1] or 0),
        )
        for row in rows
    ]
    return ApiResponse(data=items)


@router.get(
    "/compare/years",
    response_model=ApiResponse[list[YearCompareItem]],
)
async def compare_years(
    metric: YearMetricLiteral = Query(default="total"),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[list[YearCompareItem]]:
    """GROUP BY year 回每年金額或交易筆數（ASC by year）。"""
    year_expr = func.substr(Bill.billing_month, 1, 4)
    if metric == "count":
        agg = func.count(Transaction.id)
    else:
        agg = func.coalesce(func.sum(Transaction.amount), 0)

    stmt = (
        select(year_expr, agg)
        .join(Transaction, Transaction.bill_id == Bill.id)
        .group_by(year_expr)
        .order_by(year_expr.asc())
    )
    rows = (await session.execute(stmt)).all()
    items = [YearCompareItem(year=int(row[0]), value=int(row[1] or 0)) for row in rows]
    return ApiResponse(data=items)


def _period_window(period: TopMerchantPeriodLiteral, offset_months: int) -> str | None:
    """計算 period filter 的起始月（YYYY-MM 字面值），all 回 None 不過濾。"""
    if period == "all":
        return None
    today = date.today()
    if period == "month":
        m = today.month - offset_months
        y = today.year
        while m <= 0:
            m += 12
            y -= 1
        return f"{y:04d}-{m:02d}"
    # year
    return f"{today.year - offset_months:04d}"


@router.get(
    "/top-merchants",
    response_model=ApiResponse[list[TopMerchantItem]],
)
async def top_merchants(
    limit: int = Query(default=10, ge=1, le=100),
    period: TopMerchantPeriodLiteral = Query(default="all"),
    offset_months: int = Query(default=0, ge=0, le=120),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[list[TopMerchantItem]]:
    """GROUP BY merchant 取 top N（DESC by total）。"""
    stmt = (
        select(
            Transaction.merchant,
            func.coalesce(func.sum(Transaction.amount), 0).label("total"),
            func.count(Transaction.id).label("cnt"),
        )
        .join(Bill, Transaction.bill_id == Bill.id)
        .group_by(Transaction.merchant)
        .order_by(func.sum(Transaction.amount).desc())
        .limit(limit)
    )

    window = _period_window(period, offset_months)
    if window is not None and period == "month":
        stmt = stmt.where(Bill.billing_month == window)
    elif window is not None and period == "year":
        stmt = stmt.where(Bill.billing_month.startswith(f"{window}-"))

    rows = (await session.execute(stmt)).all()
    items = [
        TopMerchantItem(merchant=row[0], total=int(row[1] or 0), count=int(row[2] or 0))
        for row in rows
    ]
    return ApiResponse(data=items)
