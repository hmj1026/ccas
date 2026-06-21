"""Transactions API：交易查詢、篩選、分頁。

CSV / xlsx 匯出由 ``ccas.api.routers.exports`` 提供（see §8）。
"""

import math

from fastapi import APIRouter, Depends, Query
from sqlalchemy import asc, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.api.deps import PaginationParams
from ccas.api.schemas import (
    PaginatedResponse,
    PaginationMeta,
    SortLiteral,
    TransactionItem,
)
from ccas.storage.database import get_db_session
from ccas.storage.models import Bill, Transaction

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


def _build_filter_stmt(
    month: str | None,
    year: int | None,
    bank_code: str | None,
    category: str | None,
    q: str | None,
):
    """建立共用的交易查詢條件。month 優先於 year。"""
    stmt = select(Transaction, Bill.bank_code, Bill.billing_month).join(
        Bill, Transaction.bill_id == Bill.id
    )
    if month is not None:
        stmt = stmt.where(Bill.billing_month == month)
    elif year is not None:
        stmt = stmt.where(Bill.billing_month.startswith(f"{year}-"))
    if bank_code:
        stmt = stmt.where(Bill.bank_code == bank_code)
    if category:
        stmt = stmt.where(Transaction.category == category)
    if q:
        stmt = stmt.where(Transaction.merchant.contains(q))
    return stmt


def _to_item(row) -> TransactionItem:
    txn, bank_code, billing_month = row._tuple()
    return TransactionItem(
        id=txn.id,
        bill_id=txn.bill_id,
        trans_date=txn.trans_date,
        posting_date=txn.posting_date,
        merchant=txn.merchant,
        amount=txn.amount,
        currency=txn.currency,
        original_amount=txn.original_amount,
        card_last4=txn.card_last4,
        category=txn.category,
        bank_code=bank_code,
        billing_month=billing_month,
    )


@router.get("", response_model=PaginatedResponse[TransactionItem])
async def list_transactions(
    month: str | None = Query(
        default=None,
        description="月份（YYYY-MM），與 year 互斥，month 優先",
        pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
    ),
    year: int | None = Query(default=None, ge=2000, le=2099, description="年度篩選"),
    pagination: PaginationParams = Depends(),
    bank_code: str | None = Query(default=None),
    category: str | None = Query(default=None),
    q: str | None = Query(
        default=None,
        min_length=2,
        description="商家名稱搜尋（至少 2 字元，避免昂貴的全表掃描）",
    ),
    sort: SortLiteral = Query(default="trans_date_desc", description="排序"),
    session: AsyncSession = Depends(get_db_session),
):
    """查詢交易明細，支援月份、年度、銀行、分類篩選與分頁。"""
    base = _build_filter_stmt(month, year, bank_code, category, q)

    # 排序
    sort_column, sort_dir = _parse_sort(sort)
    base = base.order_by(sort_dir(sort_column))

    # 計算總數
    count_stmt = select(func.count()).select_from(base.subquery())
    total = (await session.execute(count_stmt)).scalar() or 0
    total_pages = max(1, math.ceil(total / pagination.page_size))

    # 分頁
    paginated = base.offset(pagination.offset).limit(pagination.page_size)
    result = await session.execute(paginated)
    items = [_to_item(row) for row in result.all()]

    return PaginatedResponse(
        data=items,
        pagination=PaginationMeta(
            page=pagination.page,
            page_size=pagination.page_size,
            total=total,
            total_pages=total_pages,
        ),
    )


def _parse_sort(sort: SortLiteral):
    """解析排序參數，回傳 (column, direction_func)。

    合法值由 ``SortLiteral`` 在 FastAPI 層保證（非法值回 422），
    此處不再做靜默 fallback；意外值直接 KeyError fail-fast。
    """
    sort_map = {
        "trans_date": Transaction.trans_date,
        "amount": Transaction.amount,
        "merchant": Transaction.merchant,
    }
    col_name, direction = sort.rsplit("_", 1)
    column = sort_map[col_name]
    dir_func = desc if direction == "desc" else asc
    return column, dir_func
