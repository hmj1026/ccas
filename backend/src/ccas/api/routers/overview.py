"""Overview API：提供 dashboard 首頁摘要資料。"""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.api.schemas import ApiResponse, OverviewData, UpcomingBillItem
from ccas.storage.database import get_db_session
from ccas.storage.models import Bill
from ccas.storage.queries import fetch_bank_names

router = APIRouter(prefix="/api", tags=["overview"])


@router.get("/overview", response_model=ApiResponse[OverviewData])
async def get_overview(
    month: str | None = Query(
        default=None,
        description=(
            "月份（YYYY-MM），省略則預設當月；當月無資料時 fallback 最近有資料月份"
        ),
        pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
    ),
    session: AsyncSession = Depends(get_db_session),
):
    """取得指定月份的摘要卡片資料與即將到期帳單。"""
    if month is None:
        today = date.today()
        current_month = today.strftime("%Y-%m")
        # 確認當月是否有帳單，無則 fallback 最近有資料月份
        has_current = (
            await session.execute(
                select(Bill.id).where(Bill.billing_month == current_month).limit(1)
            )
        ).scalar_one_or_none()
        if has_current is not None:
            month = current_month
        else:
            latest = (
                await session.execute(
                    select(Bill.billing_month)
                    .order_by(Bill.billing_month.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            month = latest or current_month
    bank_names = await fetch_bank_names(session)

    # 月份摘要：SQL 聚合，避免將整月帳單載入記憶體再於 Python 加總。
    # coalesce 確保無資料月份回 0（非 None）。
    summary_stmt = select(
        func.coalesce(func.sum(Bill.total_amount), 0),
        func.coalesce(
            func.sum(case((Bill.is_paid.is_(True), Bill.total_amount), else_=0)), 0
        ),
        # 未繳取「非已繳」的補集（else_），確保 paid + unpaid == spending 不變量，
        # 並與舊碼 `if not b.is_paid` 語意一致。
        func.coalesce(
            func.sum(case((Bill.is_paid.is_(True), 0), else_=Bill.total_amount)), 0
        ),
    ).where(Bill.billing_month == month)
    total_spending, total_paid, total_unpaid = (
        await session.execute(summary_stmt)
    ).one()

    # 即將到期帳單（未來 7 天內未繳）
    today = date.today()
    deadline = today + timedelta(days=7)
    upcoming_stmt = (
        select(Bill)
        .where(
            Bill.is_paid.is_(False),
            Bill.due_date >= today,
            Bill.due_date <= deadline,
        )
        .order_by(Bill.due_date, Bill.bank_code)
    )
    upcoming_result = await session.execute(upcoming_stmt)
    upcoming_bills = upcoming_result.scalars().all()

    data = OverviewData(
        month=month,
        total_spending=total_spending,
        total_paid=total_paid,
        total_unpaid=total_unpaid,
        upcoming_bills=[
            UpcomingBillItem(
                id=b.id,
                bank_code=b.bank_code,
                bank_name=bank_names.get(b.bank_code),
                billing_month=b.billing_month,
                total_amount=b.total_amount,
                due_date=b.due_date,
                is_paid=b.is_paid,
            )
            for b in upcoming_bills
        ],
    )
    return ApiResponse(data=data)
