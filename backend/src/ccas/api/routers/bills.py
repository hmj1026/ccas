"""Bills API：帳單列表、狀態更新、PDF 下載。"""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.api.deps import CommonMonthParams
from ccas.api.schemas import (
    ApiResponse,
    BillItem,
    BillUpdateRequest,
)
from ccas.config import get_settings
from ccas.storage.database import get_db_session
from ccas.storage.models import BankConfig, Bill

router = APIRouter(prefix="/api/bills", tags=["bills"])


def _resolve_bill_pdf_path(file_path: str, allowed_root: str) -> Path:
    """解析並驗證帳單 PDF 路徑是否仍位於允許根目錄下。"""
    pdf_path = Path(file_path).resolve()
    root_path = Path(allowed_root).resolve()
    try:
        pdf_path.relative_to(root_path)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="PDF 路徑不在允許範圍內") from exc
    if not pdf_path.is_file():
        raise HTTPException(status_code=404, detail="PDF 檔案不存在")
    return pdf_path


@router.get("", response_model=ApiResponse[list[BillItem]])
async def list_bills(
    params: CommonMonthParams = Depends(),
    status: str = Query(
        default="all",
        pattern="^(all|paid|unpaid)$",
        description="帳單狀態篩選",
    ),
    session: AsyncSession = Depends(get_db_session),
):
    """取得指定月份的帳單清單。"""
    bank_names = await _fetch_bank_names(session)

    stmt = (
        select(Bill).where(Bill.billing_month == params.month).order_by(Bill.bank_code)
    )
    if status == "unpaid":
        stmt = stmt.where(Bill.is_paid.is_(False))
    elif status == "paid":
        stmt = stmt.where(Bill.is_paid.is_(True))

    result = await session.execute(stmt)
    bills = result.scalars().all()

    data = [_to_bill_item(b, bank_names) for b in bills]
    return ApiResponse(data=data)


@router.patch("/{bill_id}", response_model=ApiResponse[BillItem])
async def update_bill(
    bill_id: int,
    body: BillUpdateRequest,
    session: AsyncSession = Depends(get_db_session),
):
    """更新帳單付款狀態。"""
    bill = await _get_bill_or_404(session, bill_id)
    bank_names = await _fetch_bank_names(session)

    bill.is_paid = body.is_paid
    await session.commit()
    await session.refresh(bill)

    return ApiResponse(data=_to_bill_item(bill, bank_names))


@router.get("/{bill_id}/pdf")
async def download_bill_pdf(
    bill_id: int,
    session: AsyncSession = Depends(get_db_session),
):
    """下載帳單原始 PDF 檔案。"""
    bill = await _get_bill_or_404(session, bill_id)

    if not bill.file_path:
        raise HTTPException(status_code=404, detail="此帳單沒有對應的 PDF 檔案")

    # 僅允許讀取 staging 根目錄下的 PDF 檔案
    settings = get_settings()
    pdf_path = _resolve_bill_pdf_path(bill.file_path, settings.staging_dir)

    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        filename=pdf_path.name,
    )


def _to_bill_item(bill: Bill, bank_names: dict[str, str]) -> BillItem:
    pdf_url = f"/api/bills/{bill.id}/pdf" if bill.file_path else None
    return BillItem(
        id=bill.id,
        bank_code=bill.bank_code,
        bank_name=bank_names.get(bill.bank_code),
        billing_month=bill.billing_month,
        total_amount=bill.total_amount,
        due_date=bill.due_date,
        is_paid=bill.is_paid,
        pdf_url=pdf_url,
        created_at=bill.created_at,
    )


async def _get_bill_or_404(session: AsyncSession, bill_id: int) -> Bill:
    stmt = select(Bill).where(Bill.id == bill_id)
    result = await session.execute(stmt)
    bill = result.scalar_one_or_none()
    if bill is None:
        raise HTTPException(status_code=404, detail=f"找不到帳單 #{bill_id}")
    return bill


async def _fetch_bank_names(session: AsyncSession) -> dict[str, str]:
    stmt = select(BankConfig.bank_code, BankConfig.bank_name)
    result = await session.execute(stmt)
    return {row[0]: row[1] for row in result.all()}
