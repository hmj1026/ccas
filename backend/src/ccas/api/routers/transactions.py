"""Transactions API：交易查詢、篩選、分頁與 CSV 匯出。"""

import csv
import io
import math

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.api.deps import PaginationParams
from ccas.api.schemas import (
    PaginatedResponse,
    PaginationMeta,
    TransactionItem,
)
from ccas.storage.database import get_db_session
from ccas.storage.models import Bill, Transaction

router = APIRouter(prefix="/api", tags=["transactions"])


def _build_filter_stmt(
    month: str | None,
    year: int | None,
    bank_code: str | None,
    category: str | None,
    q: str | None,
):
    """建立共用的交易查詢條件。month 優先於 year。"""
    stmt = (
        select(Transaction, Bill.bank_code, Bill.billing_month)
        .join(Bill, Transaction.bill_id == Bill.id)
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


@router.get("/transactions", response_model=PaginatedResponse[TransactionItem])
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
    q: str | None = Query(default=None, description="商家名稱搜尋"),
    sort: str = Query(default="trans_date_desc", description="排序"),
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


@router.get("/transactions/export")
async def export_transactions(
    month: str | None = Query(
        default=None,
        description="月份（YYYY-MM），與 year 互斥，month 優先",
        pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
    ),
    year: int | None = Query(default=None, ge=2000, le=2099, description="年度篩選"),
    bank_code: str | None = Query(default=None),
    category: str | None = Query(default=None),
    q: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
):
    """匯出交易明細為 CSV（UTF-8 with BOM）。"""
    base = _build_filter_stmt(month, year, bank_code, category, q)
    base = base.order_by(Transaction.trans_date)
    result = await session.execute(base)
    items = [_to_item(row) for row in result.all()]

    output = io.StringIO()
    # UTF-8 BOM
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow(
        [
            "交易日期",
            "記帳日期",
            "商家名稱",
            "金額",
            "幣別",
            "分類",
            "銀行代碼",
            "帳單月份",
        ]
    )
    for item in items:
        writer.writerow(
            [
                item.trans_date.isoformat(),
                item.posting_date.isoformat() if item.posting_date else "",
                item.merchant,
                item.amount,
                item.currency,
                item.category or "",
                item.bank_code,
                item.billing_month,
            ]
        )

    filename = f"ccas-transactions-{month or 'all'}"
    if bank_code:
        filename += f"-{bank_code}"
    filename += ".csv"

    content = output.getvalue().encode("utf-8-sig")
    return StreamingResponse(
        io.BytesIO(content),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _parse_sort(sort: str):
    """解析排序參數，回傳 (column, direction_func)。"""
    from sqlalchemy import asc, desc

    sort_map = {
        "trans_date": Transaction.trans_date,
        "amount": Transaction.amount,
        "merchant": Transaction.merchant,
    }
    parts = sort.rsplit("_", 1)
    if len(parts) == 2 and parts[1] in ("asc", "desc"):
        col_name, direction = parts
    else:
        col_name, direction = sort, "desc"

    # 處理 trans_date_desc 等複合名稱
    if col_name not in sort_map:
        # 嘗試去掉最後的方向再找一次
        col_name2 = sort.rsplit("_", 2)
        if len(col_name2) >= 2:
            candidate = "_".join(col_name2[:-1])
            if candidate in sort_map:
                col_name = candidate
                direction = col_name2[-1]

    column = sort_map.get(col_name, Transaction.trans_date)
    dir_func = desc if direction == "desc" else asc
    return column, dir_func
