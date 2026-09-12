"""Transactions API：交易查詢、篩選、分頁。

CSV / xlsx 匯出由 ``ccas.api.routers.exports`` 提供（see §8）。
"""

from typing import Any, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import asc, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.api.deps import PaginationParams
from ccas.api.schemas import (
    PaginatedResponse,
    PaginationMeta,
    SortLiteral,
    TransactionItem,
)
from ccas.services.schemas import AgentQueryError, AgentTransaction
from ccas.services.transactions import query_transactions
from ccas.storage.database import get_db_session
from ccas.storage.models import Bill, Transaction

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


def _handle_agent_query_error(exc: AgentQueryError) -> NoReturn:
    if exc.code == "resource_not_found":
        raise HTTPException(status_code=404, detail=exc.message)
    if exc.code == "invalid_argument":
        raise HTTPException(status_code=422, detail=exc.message)
    raise HTTPException(status_code=500, detail=exc.message)


def _agent_transaction_to_item(
    item: AgentTransaction,
    rest_metadata: dict[str, Any],
) -> TransactionItem:
    meta = rest_metadata.get(str(item.id), {})
    currency = meta.get("currency", "TWD")
    orig_amount = (
        int(item.original_amount.value) if item.original_amount is not None else None
    )
    return TransactionItem(
        id=item.id,
        bill_id=item.bill_id,
        trans_date=item.trans_date,
        posting_date=item.posting_date,
        merchant=item.merchant,
        amount=int(item.amount.value),
        currency=currency,
        original_amount=orig_amount,
        card_last4=item.card_last4,
        category=item.category,
        bank_code=item.bank_code,
        billing_month=item.billing_month,
        installment_current=item.installment_current,
        installment_total=item.installment_total,
    )


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
        installment_current=txn.installment_current,
        installment_total=txn.installment_total,
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
) -> PaginatedResponse[TransactionItem]:
    """查詢交易明細，支援月份、年度、銀行、分類篩選與分頁。"""
    try:
        projection = await query_transactions(
            session,
            month=month,
            year=year,
            bank_code=bank_code,
            category=category,
            q=q,
            sort=sort,
            page=pagination.page,
            page_size=pagination.page_size,
        )
    except AgentQueryError as exc:
        _handle_agent_query_error(exc)

    items = [
        _agent_transaction_to_item(item, projection.rest_metadata)
        for item in projection.payload.data
    ]
    return PaginatedResponse(
        data=items,
        pagination=PaginationMeta(
            page=projection.payload.pagination.page,
            page_size=projection.payload.pagination.page_size,
            total=projection.payload.pagination.total,
            total_pages=projection.payload.pagination.total_pages,
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
