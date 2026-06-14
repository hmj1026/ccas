"""Transaction export API（bills-management-and-insights §8）。

提供 CSV / xlsx 兩種格式的交易匯出：

- ``GET /api/transactions/export?format=csv``：``StreamingResponse`` +
  ``csv.writer``，逐筆 yield 避免大量資料 OOM。
- ``GET /api/transactions/export?format=xlsx``：``openpyxl.Workbook
  (write_only=True)`` 寫入 tempfile，再以 ``StreamingResponse`` 回傳。

Query params：
- ``start`` / ``end``：``YYYY-MM-DD`` 範圍（含端點）
- ``bank``：``bank_code``
- ``category``：``Transaction.category`` 字串完全相等
- ``include_user_fields``：true 時加入 manual_category_override / tags /
  merchant_alias / note 四欄。
"""

from __future__ import annotations

import csv
import io
import json
import logging
import tempfile
from collections.abc import AsyncIterator
from datetime import date
from typing import Any

import openpyxl
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.api.schemas import ExportFormatLiteral
from ccas.storage.database import get_db_session
from ccas.storage.models import Bill, Transaction

router = APIRouter(prefix="/api/transactions", tags=["exports"])
logger = logging.getLogger(__name__)

BASE_COLUMNS: tuple[str, ...] = (
    "trans_date",
    "posting_date",
    "bank_code",
    "billing_month",
    "merchant",
    "amount",
    "currency",
    "original_amount",
    "card_last4",
    "category",
)
USER_COLUMNS: tuple[str, ...] = (
    "manual_category_override",
    "tags",
    "merchant_alias",
    "note",
)

# OWASP CSV/Formula Injection 防護：試算表軟體會把以這些字元開頭的儲存格
# 當成公式執行（=cmd|... / +HYPERLINK / @SUM / -2+3 等）。匯出前在前面補一個
# 單引號讓其被當作純文字。Tab / CR 亦可觸發部分軟體的公式解析。
_FORMULA_PREFIXES: tuple[str, ...] = ("=", "+", "-", "@", "\t", "\r")


def _neutralize(value: Any) -> Any:
    """Prefix a single quote to formula-leading strings; pass non-str through."""
    if isinstance(value, str) and value and value[0] in _FORMULA_PREFIXES:
        return "'" + value
    return value


def _build_query(
    *,
    start: date | None,
    end: date | None,
    bank: str | None,
    category: str | None,
) -> Select[Any]:
    """Build the SELECT statement applying filter params."""
    stmt = (
        select(Transaction, Bill.bank_code, Bill.billing_month)
        .join(Bill, Transaction.bill_id == Bill.id)
        .order_by(Transaction.trans_date.asc(), Transaction.id.asc())
    )
    if start is not None:
        stmt = stmt.where(Transaction.trans_date >= start)
    if end is not None:
        stmt = stmt.where(Transaction.trans_date <= end)
    if bank is not None:
        stmt = stmt.where(Bill.bank_code == bank)
    if category is not None:
        stmt = stmt.where(Transaction.category == category)
    return stmt


def _row_values(
    txn: Transaction,
    bank_code: str,
    billing_month: str,
    *,
    include_user_fields: bool,
) -> list[Any]:
    base: list[Any] = [
        txn.trans_date.isoformat() if txn.trans_date else "",
        txn.posting_date.isoformat() if txn.posting_date else "",
        bank_code,
        billing_month,
        txn.merchant,
        txn.amount,
        txn.currency,
        txn.original_amount if txn.original_amount is not None else "",
        txn.card_last4 or "",
        txn.category or "",
    ]
    if include_user_fields:
        tags_str = json.dumps(list(txn.tags or []), ensure_ascii=False)
        base.extend(
            [
                "true" if txn.manual_category_override else "false",
                tags_str,
                txn.merchant_alias or "",
                txn.note or "",
            ]
        )
    return [_neutralize(v) for v in base]


async def _csv_streaming(
    session: AsyncSession,
    stmt: Select[Any],
    *,
    include_user_fields: bool,
) -> AsyncIterator[bytes]:
    """Yield CSV rows as bytes, one chunk at a time."""
    columns = list(BASE_COLUMNS)
    if include_user_fields:
        columns.extend(USER_COLUMNS)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(columns)
    yield buf.getvalue().encode("utf-8")
    buf.seek(0)
    buf.truncate()

    result = await session.stream(stmt)
    async for txn, bank_code, billing_month in result:
        writer.writerow(
            _row_values(
                txn,
                bank_code,
                billing_month,
                include_user_fields=include_user_fields,
            )
        )
        yield buf.getvalue().encode("utf-8")
        buf.seek(0)
        buf.truncate()


async def _xlsx_response(
    session: AsyncSession,
    stmt: Select[Any],
    *,
    include_user_fields: bool,
) -> StreamingResponse:
    """Build xlsx via openpyxl write_only mode + tempfile, then stream back."""
    columns = list(BASE_COLUMNS)
    if include_user_fields:
        columns.extend(USER_COLUMNS)

    tmp = tempfile.NamedTemporaryFile(  # noqa: SIM115
        suffix=".xlsx", delete=False
    )
    tmp_path = tmp.name
    tmp.close()

    wb = openpyxl.Workbook(write_only=True)
    ws = wb.create_sheet("transactions")
    ws.append(columns)

    result = await session.stream(stmt)
    async for txn, bank_code, billing_month in result:
        ws.append(
            _row_values(
                txn,
                bank_code,
                billing_month,
                include_user_fields=include_user_fields,
            )
        )

    wb.save(tmp_path)
    wb.close()

    async def _iter_xlsx() -> AsyncIterator[bytes]:
        try:
            with open(tmp_path, "rb") as fh:
                while True:
                    chunk = fh.read(64 * 1024)
                    if not chunk:
                        break
                    yield chunk
        finally:
            try:
                import os

                os.unlink(tmp_path)
            except OSError:
                logger.warning("Failed to remove tempfile %s", tmp_path)

    return StreamingResponse(
        _iter_xlsx(),
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition": "attachment; filename=transactions.xlsx",
        },
    )


@router.get("/export")
async def export_transactions(
    format: ExportFormatLiteral = Query(default="csv"),
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    bank: str | None = Query(default=None, max_length=32),
    category: str | None = Query(default=None, max_length=64),
    include_user_fields: bool = Query(default=False),
    session: AsyncSession = Depends(get_db_session),
):
    """Stream transactions as CSV or xlsx with optional filters."""
    stmt = _build_query(start=start, end=end, bank=bank, category=category)

    if format == "csv":
        return StreamingResponse(
            _csv_streaming(session, stmt, include_user_fields=include_user_fields),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": "attachment; filename=transactions.csv",
            },
        )

    return await _xlsx_response(session, stmt, include_user_fields=include_user_fields)
