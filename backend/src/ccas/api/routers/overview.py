"""Overview API：提供 dashboard 首頁摘要資料。"""

from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.api.deps import CommonMonthParams
from ccas.api.schemas import ApiResponse, OverviewData, UpcomingBillItem
from ccas.storage.database import get_db_session
from ccas.storage.models import Bill
from ccas.storage.queries import fetch_bank_names

router = APIRouter(prefix="/api", tags=["overview"])


@router.get("/overview", response_model=ApiResponse[OverviewData])
async def get_overview(
    params: CommonMonthParams = Depends(),
    session: AsyncSession = Depends(get_db_session),
):
    """取得指定月份的摘要卡片資料與即將到期帳單。"""
    month = params.month
    bank_names = await fetch_bank_names(session)

    # 月份摘要
    stmt = select(Bill).where(Bill.billing_month == month)
    result = await session.execute(stmt)
    bills = result.scalars().all()

    total_spending = sum(b.total_amount for b in bills)
    total_paid = sum(b.total_amount for b in bills if b.is_paid)
    total_unpaid = sum(b.total_amount for b in bills if not b.is_paid)

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
