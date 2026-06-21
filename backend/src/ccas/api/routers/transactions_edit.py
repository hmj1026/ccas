"""Transaction 編輯 API（bills-management-and-insights §3）。

對單筆 ``transactions`` row 提供：

- ``GET /api/transactions/{id}``：詳情頁讀取（含使用者編輯欄位）
- ``PATCH /api/transactions/{id}``：partial update
  （category/note/tags/merchant_alias）；
  若 body 包含 ``category_id``，同步將 ``manual_category_override`` 設為 ``True``，
  使後續 ``run_classify_job`` 自動跳過該筆，保留使用者編輯結果。
- ``POST /api/transactions/{id}/note``：簡化常用 note 編輯（不影響 manual_override）。
- ``DELETE /api/transactions/{id}/manual-override``：清除 flag 並即時走一次
  ``user_rules → engine`` 的 classify 邏輯，與 pipeline 完全一致。

所有端點都套上 ``verify_token`` dependency（透過 router 全域 dependency）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.api.schemas import (
    ApiResponse,
    TransactionDetailItem,
    TransactionNoteRequest,
    TransactionUpdateRequest,
)
from ccas.classifier.engine import classify
from ccas.classifier.rules import load_rules
from ccas.classifier.user_rules import UserRuleMatcher
from ccas.storage.database import get_db_session
from ccas.storage.models import Bill, Category, Transaction

router = APIRouter(prefix="/api/transactions", tags=["transactions-edit"])


def _to_detail(txn: Transaction, bill: Bill) -> TransactionDetailItem:
    return TransactionDetailItem(
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
        bank_code=bill.bank_code,
        billing_month=bill.billing_month,
        note=txn.note,
        manual_category_override=txn.manual_category_override,
        tags=list(txn.tags or []),
        merchant_alias=txn.merchant_alias,
        updated_at=txn.updated_at,
    )


async def _load_with_bill(
    session: AsyncSession, transaction_id: int
) -> tuple[Transaction, Bill]:
    """取出 Transaction + 對應 Bill；任一不存在則拋 404。"""
    stmt = (
        select(Transaction, Bill)
        .join(Bill, Transaction.bill_id == Bill.id)
        .where(Transaction.id == transaction_id)
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        raise HTTPException(status_code=404, detail="交易不存在")
    return row[0], row[1]


@router.get(
    "/{transaction_id}",
    response_model=ApiResponse[TransactionDetailItem],
)
async def get_transaction(
    transaction_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[TransactionDetailItem]:
    """讀取單筆交易詳情（含使用者編輯欄位）。"""
    txn, bill = await _load_with_bill(session, transaction_id)
    return ApiResponse(data=_to_detail(txn, bill))


@router.patch(
    "/{transaction_id}",
    response_model=ApiResponse[TransactionDetailItem],
)
async def update_transaction(
    transaction_id: int,
    body: TransactionUpdateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[TransactionDetailItem]:
    """Partial update。提供 ``category_id`` 時同步 ``manual_category_override = true``。

    - 不存在 → 404
    - ``category_id`` 對應的 Category row 不存在 → 422
    """
    txn, bill = await _load_with_bill(session, transaction_id)

    if body.category_id is not None:
        cat = await session.get(Category, body.category_id)
        if cat is None:
            raise HTTPException(
                status_code=422, detail=f"category_id={body.category_id} 不存在"
            )
        txn.category = cat.category
        txn.manual_category_override = True
    if body.note is not None:
        txn.note = body.note
    if body.tags is not None:
        txn.tags = body.tags
    if body.merchant_alias is not None:
        txn.merchant_alias = body.merchant_alias

    await session.commit()
    await session.refresh(txn)
    return ApiResponse(data=_to_detail(txn, bill))


@router.post(
    "/{transaction_id}/note",
    response_model=ApiResponse[TransactionDetailItem],
)
async def set_transaction_note(
    transaction_id: int,
    body: TransactionNoteRequest,
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[TransactionDetailItem]:
    """僅更新 note 欄位（不影響 manual_category_override）。"""
    txn, bill = await _load_with_bill(session, transaction_id)
    txn.note = body.note
    await session.commit()
    await session.refresh(txn)
    return ApiResponse(data=_to_detail(txn, bill))


@router.delete(
    "/{transaction_id}/manual-override",
    response_model=ApiResponse[TransactionDetailItem],
)
async def clear_manual_override(
    transaction_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[TransactionDetailItem]:
    """清除 manual_override flag，並即時重新走 user_rules → engine classify。

    與 pipeline 中 ``run_classify_job`` 行為完全一致，確保使用者按下重置後
    立即看到的分類結果，會等於下次 pipeline 跑出的結果。
    """
    txn, bill = await _load_with_bill(session, transaction_id)

    txn.manual_category_override = False

    user_matcher = await UserRuleMatcher.load(session)
    user_category = await user_matcher.match(txn.merchant)
    if user_category is not None:
        txn.category = user_category
    else:
        rule_set = await load_rules(session)
        txn.category = classify(txn.merchant, rule_set)

    await session.commit()
    await session.refresh(txn)
    return ApiResponse(data=_to_detail(txn, bill))
