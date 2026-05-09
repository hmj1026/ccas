"""Budgets API（bills-management-and-insights §6）。

CRUD for ``budgets`` 表 + current-period 累計 + alert acknowledge：

- ``GET /api/budgets``：列表，可選 ``?scope=`` filter
- ``POST /api/budgets``：新增（驗證 scope/scope_ref 一致）
- ``PUT /api/budgets/{id}``：partial update
- ``DELETE /api/budgets/{id}``：刪除
- ``GET /api/budgets/{id}/current-period``：當月累計 + threshold 狀態
- ``GET /api/budgets/alerts/active``：未確認 alert 列表
- ``POST /api/budgets/alerts/{id}/acknowledge``：確認 alert

scope_ref 驗證規則：
- ``monthly_total`` 必為 NULL
- ``monthly_category`` 必對應 ``categories.category`` 字串
- ``monthly_bank`` 必對應 ``bank_configs.bank_code``
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.api.schemas import (
    ApiResponse,
    BudgetAlertItem,
    BudgetCreateRequest,
    BudgetCurrentPeriod,
    BudgetItem,
    BudgetScopeLiteral,
    BudgetUpdateRequest,
)
from ccas.storage.database import get_db_session
from ccas.storage.models import (
    BankConfig,
    Bill,
    Budget,
    BudgetAlert,
    BudgetScope,
    Category,
    Transaction,
)

router = APIRouter(prefix="/api/budgets", tags=["budgets"])


def _scope_str(scope: BudgetScope | str) -> BudgetScopeLiteral:
    val = scope.value if isinstance(scope, BudgetScope) else str(scope)
    if val not in ("monthly_total", "monthly_category", "monthly_bank"):
        return "monthly_total"
    return val  # type: ignore[return-value]


def _to_item(b: Budget) -> BudgetItem:
    return BudgetItem(
        id=b.id,
        scope=_scope_str(b.scope),
        scope_ref=b.scope_ref,
        amount_minor_units=b.amount_minor_units,
        alert_threshold_percent=b.alert_threshold_percent,
        enabled=b.enabled,
        created_at=b.created_at,
        updated_at=b.updated_at,
    )


async def _validate_scope_ref(
    session: AsyncSession,
    scope: BudgetScopeLiteral,
    scope_ref: str | None,
) -> None:
    """Enforce scope_ref domain rules; raises HTTP 422 on violation."""
    if scope == "monthly_total":
        if scope_ref is not None:
            raise HTTPException(
                status_code=422, detail="monthly_total 不得提供 scope_ref"
            )
        return

    if scope_ref is None or scope_ref.strip() == "":
        raise HTTPException(
            status_code=422,
            detail=f"{scope} 必須提供 scope_ref",
        )

    if scope == "monthly_category":
        cat_stmt = select(Category.id).where(Category.category == scope_ref)
        result = await session.execute(cat_stmt)
        if result.scalar_one_or_none() is None:
            raise HTTPException(status_code=422, detail=f"未知 category：{scope_ref}")
    elif scope == "monthly_bank":
        bank_stmt = select(BankConfig.id).where(BankConfig.bank_code == scope_ref)
        result = await session.execute(bank_stmt)
        if result.scalar_one_or_none() is None:
            raise HTTPException(status_code=422, detail=f"未知 bank_code：{scope_ref}")


@router.get("", response_model=ApiResponse[list[BudgetItem]])
async def list_budgets(
    scope: BudgetScopeLiteral | None = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[list[BudgetItem]]:
    """列出全部預算，可選 scope filter。"""
    stmt = select(Budget).order_by(Budget.id.asc())
    if scope is not None:
        stmt = stmt.where(Budget.scope == scope)
    rows = (await session.execute(stmt)).scalars().all()
    return ApiResponse(data=[_to_item(b) for b in rows])


@router.post(
    "",
    response_model=ApiResponse[BudgetItem],
    status_code=201,
)
async def create_budget(
    body: BudgetCreateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[BudgetItem]:
    """新增預算；scope/scope_ref 不一致 → 422。"""
    await _validate_scope_ref(session, body.scope, body.scope_ref)

    b = Budget(
        scope=BudgetScope(body.scope),
        scope_ref=body.scope_ref,
        amount_minor_units=body.amount_minor_units,
        alert_threshold_percent=body.alert_threshold_percent,
        enabled=body.enabled,
    )
    session.add(b)
    await session.commit()
    await session.refresh(b)
    return ApiResponse(data=_to_item(b))


@router.put("/{budget_id}", response_model=ApiResponse[BudgetItem])
async def update_budget(
    budget_id: int,
    body: BudgetUpdateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[BudgetItem]:
    """更新預算；不存在 → 404。"""
    b = await session.get(Budget, budget_id)
    if b is None:
        raise HTTPException(status_code=404, detail=f"budget_id={budget_id} 不存在")

    if body.scope is not None or body.scope_ref is not None:
        new_scope = body.scope or _scope_str(b.scope)
        new_ref = body.scope_ref if body.scope_ref is not None else b.scope_ref
        await _validate_scope_ref(session, new_scope, new_ref)
        if body.scope is not None:
            b.scope = BudgetScope(body.scope)
        if body.scope_ref is not None:
            b.scope_ref = body.scope_ref

    if body.amount_minor_units is not None:
        b.amount_minor_units = body.amount_minor_units
    if body.alert_threshold_percent is not None:
        b.alert_threshold_percent = body.alert_threshold_percent
    if body.enabled is not None:
        b.enabled = body.enabled

    await session.commit()
    await session.refresh(b)
    return ApiResponse(data=_to_item(b))


@router.delete("/{budget_id}", response_model=ApiResponse[dict[str, int]])
async def delete_budget(
    budget_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[dict[str, int]]:
    """刪除預算；不存在 → 404。"""
    b = await session.get(Budget, budget_id)
    if b is None:
        raise HTTPException(status_code=404, detail=f"budget_id={budget_id} 不存在")
    await session.delete(b)
    await session.commit()
    return ApiResponse(data={"deleted_id": budget_id})


def _current_year_month(today: date | None = None) -> str:
    today = today or date.today()
    return f"{today.year:04d}-{today.month:02d}"


async def _aggregate_current_period(
    session: AsyncSession,
    budget: Budget,
    period_ym: str,
) -> int:
    """計算指定 budget 在 period_ym 的累計花費（minor units, 本幣）。"""
    stmt = (
        select(func.coalesce(func.sum(Transaction.amount), 0))
        .join(Bill, Transaction.bill_id == Bill.id)
        .where(Bill.billing_month == period_ym)
    )
    if budget.scope == BudgetScope.MONTHLY_CATEGORY:
        stmt = stmt.where(Transaction.category == budget.scope_ref)
    elif budget.scope == BudgetScope.MONTHLY_BANK:
        stmt = stmt.where(Bill.bank_code == budget.scope_ref)
    result = await session.execute(stmt)
    return int(result.scalar_one() or 0)


@router.get(
    "/alerts/active",
    response_model=ApiResponse[list[BudgetAlertItem]],
)
async def list_active_alerts(
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[list[BudgetAlertItem]]:
    """回傳當月與最近 7 天內未確認的 alert。"""
    period = _current_year_month()
    stmt = (
        select(BudgetAlert, Budget)
        .join(Budget, BudgetAlert.budget_id == Budget.id)
        .where(
            BudgetAlert.acknowledged_at.is_(None),
            BudgetAlert.period_year_month == period,
        )
        .order_by(BudgetAlert.triggered_at.desc())
    )
    rows = (await session.execute(stmt)).all()
    items = [
        BudgetAlertItem(
            id=a.id,
            budget_id=b.id,
            scope=_scope_str(b.scope),
            scope_ref=b.scope_ref,
            period_year_month=a.period_year_month,
            threshold_breached_percent=a.threshold_breached_percent,
            current_amount_minor_units=a.current_amount_minor_units,
            amount_minor_units=b.amount_minor_units,
            triggered_at=a.triggered_at,
            acknowledged_at=a.acknowledged_at,
        )
        for a, b in rows
    ]
    return ApiResponse(data=items)


@router.post(
    "/alerts/{alert_id}/acknowledge",
    response_model=ApiResponse[dict[str, int]],
)
async def acknowledge_alert(
    alert_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[dict[str, int]]:
    """設定 acknowledged_at = now。"""
    alert = await session.get(BudgetAlert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail=f"alert_id={alert_id} 不存在")
    alert.acknowledged_at = datetime.now(UTC)
    await session.commit()
    return ApiResponse(data={"acknowledged_id": alert_id})


@router.get(
    "/{budget_id}/current-period",
    response_model=ApiResponse[BudgetCurrentPeriod],
)
async def get_current_period(
    budget_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[BudgetCurrentPeriod]:
    """回傳當月對應 scope 累計金額 + threshold 狀態。"""
    b = await session.get(Budget, budget_id)
    if b is None:
        raise HTTPException(status_code=404, detail=f"budget_id={budget_id} 不存在")

    period = _current_year_month()
    current = await _aggregate_current_period(session, b, period)
    percent = (
        (current / b.amount_minor_units * 100.0) if b.amount_minor_units > 0 else 0.0
    )
    return ApiResponse(
        data=BudgetCurrentPeriod(
            budget_id=b.id,
            period_year_month=period,
            amount_minor_units=b.amount_minor_units,
            current_amount_minor_units=current,
            percent=round(percent, 2),
            threshold_breached=percent >= b.alert_threshold_percent,
            alert_threshold_percent=b.alert_threshold_percent,
        )
    )
