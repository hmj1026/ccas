"""Analytics API：月趨勢、類別分布、銀行比較。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.api.schemas import (
    ApiResponse,
    BankItem,
    CategoryItem,
    CategoryWithCompareItem,
    TrendItem,
)
from ccas.constants import DEFAULT_CATEGORY
from ccas.storage.database import get_db_session
from ccas.storage.models import Bill, Transaction
from ccas.storage.queries import fetch_bank_names


def _previous_month(month: str) -> str:
    """``YYYY-MM`` → 前一個月（同樣格式）。"""
    y, m = (int(p) for p in month.split("-"))
    if m == 1:
        return f"{y - 1:04d}-12"
    return f"{y:04d}-{m - 1:02d}"


router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def _apply_month_year_filter(stmt, month: str | None, year: int | None):
    """月份 / 年度篩選：month 優先，year 次之。"""
    if month is not None:
        return stmt.where(Bill.billing_month == month)
    if year is not None:
        return stmt.where(Bill.billing_month.startswith(f"{year}-"))
    return stmt


@router.get("/years", response_model=ApiResponse[list[int]])
async def get_years(session: AsyncSession = Depends(get_db_session)):
    """回傳有帳單資料的年份清單（降序）。"""
    stmt = (
        select(func.substr(Bill.billing_month, 1, 4))
        .distinct()
        .order_by(func.substr(Bill.billing_month, 1, 4).desc())
    )
    result = await session.execute(stmt)
    data = [int(row[0]) for row in result.all()]
    return ApiResponse(data=data)


@router.get("/trend", response_model=ApiResponse[list[TrendItem]])
async def get_trend(
    months: int = Query(default=6, ge=1, le=24, description="回溯月數"),
    session: AsyncSession = Depends(get_db_session),
):
    """取得最近 N 個月的消費總額趨勢。"""
    from datetime import date

    today = date.today()
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


def _category_totals_stmt():
    """Aggregate transaction totals grouped by category (uncategorized fallback)."""
    return (
        select(
            func.coalesce(Transaction.category, DEFAULT_CATEGORY),
            func.coalesce(func.sum(Transaction.amount), 0),
        )
        .join(Bill, Transaction.bill_id == Bill.id)
        .group_by(func.coalesce(Transaction.category, DEFAULT_CATEGORY))
        .order_by(func.sum(Transaction.amount).desc())
    )


@router.get("/categories", response_model=ApiResponse[list[CategoryItem]])
async def get_categories(
    month: str | None = Query(
        default=None,
        description="月份（YYYY-MM），與 year 互斥，month 優先",
        pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
    ),
    year: int | None = Query(default=None, ge=2000, le=2099, description="年度篩選"),
    session: AsyncSession = Depends(get_db_session),
):
    """取得類別分布；月對月比較請改用 ``/categories/compare``。"""
    stmt = _apply_month_year_filter(_category_totals_stmt(), month, year)
    rows = (await session.execute(stmt)).all()
    return ApiResponse(
        data=[CategoryItem(category=row[0], total=int(row[1])) for row in rows]
    )


@router.get(
    "/categories/compare",
    response_model=ApiResponse[list[CategoryWithCompareItem]],
)
async def get_categories_compare(
    month: str = Query(
        description="月份（YYYY-MM），必填",
        pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
    ),
    session: AsyncSession = Depends(get_db_session),
):
    """取得指定月份類別分布，附前一個月的金額與變化百分比。"""
    # 單一查詢同時取本月與前一月（GROUP BY billing_month, category），
    # 再於 Python 端分桶，取代原本兩次 round-trip（R30）。
    prev_month = _previous_month(month)
    stmt = (
        select(
            Bill.billing_month,
            func.coalesce(Transaction.category, DEFAULT_CATEGORY),
            func.coalesce(func.sum(Transaction.amount), 0),
        )
        .join(Bill, Transaction.bill_id == Bill.id)
        .where(Bill.billing_month.in_([month, prev_month]))
        .group_by(
            Bill.billing_month,
            func.coalesce(Transaction.category, DEFAULT_CATEGORY),
        )
    )
    cur_by_cat: dict[str, int] = {}
    prev_by_cat: dict[str, int] = {}
    for billing_month, cat, total in (await session.execute(stmt)).all():
        bucket = cur_by_cat if billing_month == month else prev_by_cat
        bucket[cat] = int(total)

    # Iterate over the UNION of current + previous category keys (not just
    # current-month buckets). A category present last month but absent this
    # month would otherwise vanish silently; here it surfaces with total=0,
    # previous_total=<prev>, change_percent=-100.0 (full downward trend).
    # The zero-previous guard is preserved: previous_total of 0 or None yields
    # change_percent=None (no divide-by-zero, no spurious +inf).
    all_cats = set(cur_by_cat) | set(prev_by_cat)
    items: list[CategoryWithCompareItem] = []
    for cat in all_cats:
        total = cur_by_cat.get(cat, 0)
        previous = prev_by_cat.get(cat)
        if previous is None or previous == 0:
            change_pct: float | None = None
        else:
            change_pct = round((total - previous) / previous * 100.0, 2)
        items.append(
            CategoryWithCompareItem(
                category=cat,
                total=total,
                previous_total=previous,
                change_percent=change_pct,
            )
        )
    # Preserve descending-by-current-total ordering (previous-only categories
    # with total=0 sort to the bottom).
    items.sort(key=lambda item: item.total, reverse=True)
    return ApiResponse(data=items)


@router.get("/banks", response_model=ApiResponse[list[BankItem]])
async def get_banks(
    month: str | None = Query(
        default=None,
        description="月份（YYYY-MM），與 year 互斥，month 優先",
        pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
    ),
    year: int | None = Query(default=None, ge=2000, le=2099, description="年度篩選"),
    session: AsyncSession = Depends(get_db_session),
):
    """取得按銀行彙總的消費總額，可指定月份、年度或彙總全部。"""
    bank_names = await fetch_bank_names(session)

    stmt = (
        select(Bill.bank_code, func.sum(Bill.total_amount))
        .group_by(Bill.bank_code)
        .order_by(func.sum(Bill.total_amount).desc())
    )
    stmt = _apply_month_year_filter(stmt, month, year)

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
