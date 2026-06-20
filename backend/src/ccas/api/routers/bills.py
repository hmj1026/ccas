"""Bills API：帳單列表、狀態更新、PDF 下載。"""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.api.deps import PaginationParams
from ccas.api.schemas import (
    ApiResponse,
    BillItem,
    BillUpdateRequest,
    PaginatedResponse,
    PaginationMeta,
    TransactionItem,
)
from ccas.config import get_settings
from ccas.storage.database import get_db_session
from ccas.storage.models import Bill, Transaction
from ccas.storage.queries import fetch_bank_names

router = APIRouter(prefix="/api/bills", tags=["bills"])

# 防護上限：單一帳單交易明細一次最多回傳的筆數，避免異常帳單拖垮回應。
# 正常帳單遠低於此值；完整筆數另透過 X-Total-Count header 暴露。
TRANSACTIONS_HARD_LIMIT = 500


def _resolve_bill_pdf_path(file_path: str, allowed_root: str) -> Path:
    """解析並驗證帳單 PDF 路徑是否仍位於允許根目錄下。

    若儲存路徑來自不同執行環境（例如本機匯入後改跑 Docker），
    嘗試取末尾 bank_code/filename 兩段重新接到目前 staging_dir 下。
    """
    root_path = Path(allowed_root).resolve()
    pdf_path = Path(file_path).resolve()

    try:
        pdf_path.relative_to(root_path)
    except ValueError:
        # Path was stored in a different environment
        # (e.g., local absolute path in Docker).
        # Rebase using the last two path components: {bank_code}/{filename}.
        parts = pdf_path.parts
        if len(parts) >= 2:
            pdf_path = (root_path / parts[-2] / parts[-1]).resolve()
        try:
            pdf_path.relative_to(root_path)
        except ValueError as exc:
            raise HTTPException(
                status_code=403, detail="PDF 路徑不在允許範圍內"
            ) from exc

    if not pdf_path.is_file():
        raise HTTPException(status_code=404, detail="PDF 檔案不存在")
    return pdf_path


@router.get("", response_model=PaginatedResponse[BillItem])
async def list_bills(
    month: str | None = Query(
        default=None,
        description="月份（YYYY-MM），與 year 互斥，month 優先",
        pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
    ),
    year: int | None = Query(default=None, ge=2000, le=2099, description="年度篩選"),
    bank_code: str | None = Query(default=None, description="銀行代碼篩選"),
    status: str = Query(
        default="all",
        pattern="^(all|paid|unpaid)$",
        description="帳單狀態篩選",
    ),
    pagination: PaginationParams = Depends(),
    session: AsyncSession = Depends(get_db_session),
):
    """取得帳單清單，可依月份、年度、銀行與付款狀態篩選，支援分頁。"""
    bank_names = await fetch_bank_names(session)

    stmt = select(Bill).order_by(Bill.billing_month.desc(), Bill.bank_code)
    if month is not None:
        stmt = stmt.where(Bill.billing_month == month)
    elif year is not None:
        stmt = stmt.where(Bill.billing_month.startswith(f"{year}-"))
    if bank_code is not None:
        stmt = stmt.where(Bill.bank_code == bank_code)
    if status == "unpaid":
        stmt = stmt.where(Bill.is_paid.is_(False))
    elif status == "paid":
        stmt = stmt.where(Bill.is_paid.is_(True))

    total = (
        await session.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar_one()

    paged = stmt.offset(pagination.offset).limit(pagination.page_size)
    bills = (await session.execute(paged)).scalars().all()

    total_pages = max(1, (total + pagination.page_size - 1) // pagination.page_size)
    return PaginatedResponse(
        data=[_to_bill_item(b, bank_names) for b in bills],
        pagination=PaginationMeta(
            page=pagination.page,
            page_size=pagination.page_size,
            total=total,
            total_pages=total_pages,
        ),
    )


@router.patch("/{bill_id}", response_model=ApiResponse[BillItem])
async def update_bill(
    bill_id: int,
    body: BillUpdateRequest,
    session: AsyncSession = Depends(get_db_session),
):
    """更新帳單付款狀態。"""
    bill = await _get_bill_or_404(session, bill_id)
    bank_names = await fetch_bank_names(session)

    bill.is_paid = body.is_paid
    await session.commit()
    await session.refresh(bill)

    return ApiResponse(data=_to_bill_item(bill, bank_names))


@router.get(
    "/{bill_id}/transactions",
    response_model=ApiResponse[list[TransactionItem]],
)
async def list_bill_transactions(
    bill_id: int,
    response: Response,
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[list[TransactionItem]]:
    """取得指定帳單的交易明細，依交易日期升序排列。

    為避免異常帳單（極端交易筆數）拖垮回應，隱式上限為 ``TRANSACTIONS_HARD_LIMIT``
    筆；完整筆數透過 ``X-Total-Count`` header 暴露。正常帳單遠低於此上限。
    """
    await _get_bill_or_404(session, bill_id)

    total = (
        await session.execute(
            select(func.count())
            .select_from(Transaction)
            .where(Transaction.bill_id == bill_id)
        )
    ).scalar_one()

    stmt = (
        select(Transaction, Bill.bank_code, Bill.billing_month)
        .join(Bill, Transaction.bill_id == Bill.id)
        .where(Transaction.bill_id == bill_id)
        .order_by(Transaction.trans_date)
        .limit(TRANSACTIONS_HARD_LIMIT)
    )
    rows = (await session.execute(stmt)).all()
    response.headers["X-Total-Count"] = str(total)
    # 截斷時在 body 內 in-band 提示（不只靠 header），避免消費者誤判資料完整。
    message = (
        f"交易筆數超過上限，僅回傳前 {TRANSACTIONS_HARD_LIMIT} 筆（共 {total} 筆）"
        if total > TRANSACTIONS_HARD_LIMIT
        else ""
    )

    return ApiResponse(
        message=message,
        data=[
            TransactionItem(
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
            for txn, bank_code, billing_month in rows
        ],
    )


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
    """Convert a Bill ORM instance to a BillItem response schema.

    Args:
        bill: SQLAlchemy Bill model instance.
        bank_names: Mapping of bank_code to display name from BankConfig.

    Returns:
        BillItem schema with pdf_url set when a file_path is present.
    """
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
    """Fetch a Bill by ID, raising HTTP 404 if not found.

    Args:
        session: Active async database session.
        bill_id: Primary key of the bill to fetch.

    Returns:
        The matching Bill ORM instance.

    Raises:
        HTTPException: 404 if no bill with the given ID exists.
    """
    stmt = select(Bill).where(Bill.id == bill_id)
    result = await session.execute(stmt)
    bill = result.scalar_one_or_none()
    if bill is None:
        raise HTTPException(status_code=404, detail=f"找不到帳單 #{bill_id}")
    return bill
