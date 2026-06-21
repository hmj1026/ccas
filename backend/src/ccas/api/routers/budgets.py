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
from typing import cast, get_args

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select
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
    Budget,
    BudgetAlert,
    BudgetScope,
    Category,
)
from ccas.storage.queries import aggregate_current_periods

router = APIRouter(prefix="/api/budgets", tags=["budgets"])


def _scope_str(scope: BudgetScope | str) -> BudgetScopeLiteral:
    """Normalise enum / DB string to API literal; fail fast on unknown values."""
    val = scope.value if isinstance(scope, BudgetScope) else str(scope)
    if val not in get_args(BudgetScopeLiteral):
        # HTTPException (not ValueError): an unknown DB value must surface as
        # a clean 500 through FastAPI, not an unhandled exception traceback.
        raise HTTPException(
            status_code=500, detail=f"DB contains unknown budget scope: {val!r}"
        )
    return cast(BudgetScopeLiteral, val)


def _to_item(
    b: Budget, current_period: BudgetCurrentPeriod | None = None
) -> BudgetItem:
    return BudgetItem(
        id=b.id,
        scope=_scope_str(b.scope),
        scope_ref=b.scope_ref,
        amount_ntd=b.amount_ntd,
        alert_threshold_percent=b.alert_threshold_percent,
        enabled=b.enabled,
        created_at=b.created_at,
        updated_at=b.updated_at,
        current_period=current_period,
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
    include_current_period: bool = Query(default=False),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[list[BudgetItem]]:
    """列出全部預算，可選 scope filter。

    ``include_current_period=true`` 時內聯每筆當月累計（O(1) 批次查詢），
    讓前端免逐筆呼叫 ``/current-period`` 端點（消除 1+N）；預設 false 維持向下相容。
    """
    stmt = select(Budget).order_by(Budget.id.asc())
    if scope is not None:
        stmt = stmt.where(Budget.scope == scope)
    rows = list((await session.execute(stmt)).scalars().all())
    if not include_current_period:
        return ApiResponse(data=[_to_item(b) for b in rows])

    period = _current_year_month()
    current_map = await aggregate_current_periods(session, rows, period)
    return ApiResponse(
        data=[
            _to_item(b, _to_current_period(b, current_map.get(b.id, 0), period))
            for b in rows
        ]
    )


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
        amount_ntd=body.amount_ntd,
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

    if body.amount_ntd is not None:
        b.amount_ntd = body.amount_ntd
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
    # 先清除子表 BudgetAlert（FK 無 ON DELETE CASCADE，且 foreign_keys=ON 會
    # 阻擋帶子列的刪除）。alert 為內部通知去重記錄，無獨立保留價值，隨 budget
    # 一併清除。以 bulk DELETE 取代 ORM relationship cascade，避免 async 下
    # lazy-load 子集合觸發 MissingGreenlet。
    await session.execute(delete(BudgetAlert).where(BudgetAlert.budget_id == budget_id))
    await session.delete(b)
    await session.commit()
    return ApiResponse(data={"deleted_id": budget_id})


def _current_year_month(today: date | None = None) -> str:
    today = today or date.today()
    return f"{today.year:04d}-{today.month:02d}"


def _to_current_period(
    budget: Budget, current: int, period_ym: str
) -> BudgetCurrentPeriod:
    """組裝單筆 current-period（百分比 + threshold 狀態）。"""
    percent = (current / budget.amount_ntd * 100.0) if budget.amount_ntd > 0 else 0.0
    return BudgetCurrentPeriod(
        budget_id=budget.id,
        period_year_month=period_ym,
        amount_ntd=budget.amount_ntd,
        current_amount_ntd=current,
        percent=round(percent, 2),
        threshold_breached=percent >= budget.alert_threshold_percent,
        alert_threshold_percent=budget.alert_threshold_percent,
    )


@router.get(
    "/alerts/active",
    response_model=ApiResponse[list[BudgetAlertItem]],
)
async def list_active_alerts(
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[list[BudgetAlertItem]]:
    """回傳當月與最近 7 天內未確認的 alert。

    刻意不以 ``notified`` 過濾：banner 反映「門檻已超支」這個事實，與
    Telegram 是否成功推播無關。``notified=False`` 代表「已超支但推播尚未
    成功」，仍應在 dashboard 顯示（請勿加上 ``notified.is_(True)`` 過濾，
    否則推播失敗的超支警示會在 UI 消失）。
    """
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
            current_amount_ntd=a.current_amount_ntd,
            amount_ntd=b.amount_ntd,
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
    current_map = await aggregate_current_periods(session, [b], period)
    return ApiResponse(data=_to_current_period(b, current_map.get(b.id, 0), period))
