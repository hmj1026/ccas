"""Settings API：銀行設定與分類關鍵字管理。"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.api.schemas import (
    ApiResponse,
    BankConfigCreateRequest,
    BankConfigItem,
    BankConfigUpdateRequest,
    CategoryKeywordCreateRequest,
    CategoryKeywordItem,
    CategoryKeywordUpdateRequest,
)
from ccas.storage.database import get_db_session
from ccas.storage.models import BankConfig, Category

router = APIRouter(prefix="/api/settings", tags=["settings"])

# -- Banks --


@router.get("/banks", response_model=ApiResponse[list[BankConfigItem]])
async def list_banks(
    session: AsyncSession = Depends(get_db_session),
):
    """取得所有銀行設定（不含 pdf_password_rule）。"""
    stmt = select(BankConfig).order_by(BankConfig.bank_code)
    result = await session.execute(stmt)
    banks = result.scalars().all()
    data = [_to_bank_item(b) for b in banks]
    return ApiResponse(data=data)


@router.post("/banks", response_model=ApiResponse[BankConfigItem], status_code=201)
async def create_bank(
    body: BankConfigCreateRequest,
    session: AsyncSession = Depends(get_db_session),
):
    """新增銀行設定。"""
    bank = BankConfig(
        bank_code=body.bank_code,
        bank_name=body.bank_name,
        gmail_filter=body.gmail_filter,
        active_parser_version=body.active_parser_version,
        is_active=body.is_active,
    )
    session.add(bank)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail=f"銀行代碼 {body.bank_code} 已存在")
    await session.refresh(bank)
    return ApiResponse(data=_to_bank_item(bank))


@router.patch("/banks/{bank_id}", response_model=ApiResponse[BankConfigItem])
async def update_bank(
    bank_id: int,
    body: BankConfigUpdateRequest,
    session: AsyncSession = Depends(get_db_session),
):
    """更新銀行設定（僅允許 is_active 與 active_parser_version）。"""
    bank = await _get_bank_or_404(session, bank_id)

    if body.is_active is not None:
        bank.is_active = body.is_active
    if body.active_parser_version is not None:
        bank.active_parser_version = body.active_parser_version

    await session.commit()
    await session.refresh(bank)
    return ApiResponse(data=_to_bank_item(bank))


# -- Categories --


@router.get("/categories", response_model=ApiResponse[list[CategoryKeywordItem]])
async def list_categories(
    session: AsyncSession = Depends(get_db_session),
):
    """取得所有分類關鍵字。"""
    stmt = select(Category).order_by(Category.category, Category.keyword)
    result = await session.execute(stmt)
    categories = result.scalars().all()
    data = [_to_category_item(c) for c in categories]
    return ApiResponse(data=data)


@router.post(
    "/categories", response_model=ApiResponse[CategoryKeywordItem], status_code=201
)
async def create_category(
    body: CategoryKeywordCreateRequest,
    session: AsyncSession = Depends(get_db_session),
):
    """新增分類關鍵字。"""
    cat = Category(keyword=body.keyword, category=body.category)
    session.add(cat)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail=f"關鍵字 '{body.keyword}' 已存在")
    await session.refresh(cat)
    return ApiResponse(data=_to_category_item(cat))


@router.patch(
    "/categories/{category_id}", response_model=ApiResponse[CategoryKeywordItem]
)
async def update_category(
    category_id: int,
    body: CategoryKeywordUpdateRequest,
    session: AsyncSession = Depends(get_db_session),
):
    """更新分類關鍵字。"""
    cat = await _get_category_or_404(session, category_id)

    if body.keyword is not None:
        cat.keyword = body.keyword
    if body.category is not None:
        cat.category = body.category

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail=f"關鍵字 '{body.keyword}' 已存在")
    await session.refresh(cat)
    return ApiResponse(data=_to_category_item(cat))


@router.delete("/categories/{category_id}", response_model=ApiResponse[dict[str, int]])
async def delete_category(
    category_id: int,
    session: AsyncSession = Depends(get_db_session),
):
    """刪除分類關鍵字，回傳統一信封格式。

    若該 category 仍被進階分類規則 (``classification_rules.category_id``)
    引用，SQLite 的 ``foreign_keys=ON`` 會在 commit 時拋
    ``IntegrityError``，轉為 409 阻止產生孤兒規則。
    """
    cat = await _get_category_or_404(session, category_id)
    await session.delete(cat)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"分類 #{category_id} 仍被分類規則引用，無法刪除",
        ) from None
    return ApiResponse(data={"deleted_id": category_id})


# -- Helpers --


def _to_bank_item(bank: BankConfig) -> BankConfigItem:
    return BankConfigItem(
        id=bank.id,
        bank_code=bank.bank_code,
        bank_name=bank.bank_name,
        gmail_filter=bank.gmail_filter,
        active_parser_version=bank.active_parser_version,
        is_active=bank.is_active,
    )


def _to_category_item(cat: Category) -> CategoryKeywordItem:
    return CategoryKeywordItem(
        id=cat.id,
        keyword=cat.keyword,
        category=cat.category,
    )


async def _get_bank_or_404(session: AsyncSession, bank_id: int) -> BankConfig:
    stmt = select(BankConfig).where(BankConfig.id == bank_id)
    result = await session.execute(stmt)
    bank = result.scalar_one_or_none()
    if bank is None:
        raise HTTPException(status_code=404, detail=f"找不到銀行設定 #{bank_id}")
    return bank


async def _get_category_or_404(session: AsyncSession, category_id: int) -> Category:
    stmt = select(Category).where(Category.id == category_id)
    result = await session.execute(stmt)
    cat = result.scalar_one_or_none()
    if cat is None:
        raise HTTPException(status_code=404, detail=f"找不到分類關鍵字 #{category_id}")
    return cat
