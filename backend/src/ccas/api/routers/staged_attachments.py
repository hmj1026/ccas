"""Staged Attachments API：暴露 Gmail 附件 staging 狀態供前端呈現。

主要用途：讓前端能夠提醒使用者哪些附件卡在非正常狀態（例如
``fetch_expired``、``failed``、``parse_failed``），並解釋原因。刻意
**不** 暴露檔案系統路徑與 Gmail 內部識別，避免洩漏實作細節。
"""

from __future__ import annotations

from typing import cast, get_args

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.api.deps import PaginationParams
from ccas.api.schemas import (
    PaginatedResponse,
    PaginationMeta,
    StagedAttachmentItem,
    StagedAttachmentStatusLiteral,
)
from ccas.storage.database import get_db_session
from ccas.storage.models import StagedAttachment
from ccas.storage.queries import fetch_bank_names

router = APIRouter(prefix="/api/staged-attachments", tags=["staged-attachments"])

_ALLOWED_STATUSES: frozenset[str] = frozenset(get_args(StagedAttachmentStatusLiteral))


def _parse_status_csv(status_csv: str | None) -> list[str]:
    """解析逗號分隔的 status filter 並驗證白名單。"""
    if not status_csv:
        return []
    out: list[str] = []
    for raw in status_csv.split(","):
        token = raw.strip()
        if token and token in _ALLOWED_STATUSES:
            out.append(token)
    return out


def _to_item(
    record: StagedAttachment,
    bank_names: dict[str, str],
) -> StagedAttachmentItem:
    return StagedAttachmentItem(
        id=record.id,
        bank_code=record.bank_code,
        bank_name=bank_names.get(record.bank_code),
        status=cast(StagedAttachmentStatusLiteral, record.status),
        original_filename=record.original_filename,
        message_date=record.message_date,
        error_reason=record.error_reason,
        source_type=record.source_type,
        created_at=record.created_at,
    )


@router.get("", response_model=PaginatedResponse[StagedAttachmentItem])
async def list_staged_attachments(
    status: str | None = Query(
        default=None,
        description=(
            "附件狀態篩選（逗號分隔，例：fetch_expired,failed,parse_failed）。"
            "未指定時回傳全部狀態。"
        ),
    ),
    bank_code: str | None = Query(default=None, description="銀行代碼篩選"),
    pagination: PaginationParams = Depends(),
    session: AsyncSession = Depends(get_db_session),
) -> PaginatedResponse[StagedAttachmentItem]:
    """取得 staged_attachments 列表，支援 status/bank_code 過濾與分頁。

    排序：``message_date DESC, id DESC``（最新訊息優先）。
    """
    statuses = _parse_status_csv(status)
    bank_names = await fetch_bank_names(session)

    stmt = select(StagedAttachment).order_by(
        StagedAttachment.message_date.desc(),
        StagedAttachment.id.desc(),
    )
    if statuses:
        stmt = stmt.where(StagedAttachment.status.in_(statuses))
    if bank_code is not None:
        stmt = stmt.where(StagedAttachment.bank_code == bank_code)

    total = (
        await session.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar_one()

    paged = stmt.offset(pagination.offset).limit(pagination.page_size)
    records = (await session.execute(paged)).scalars().all()

    total_pages = max(1, (total + pagination.page_size - 1) // pagination.page_size)
    return PaginatedResponse(
        data=[_to_item(r, bank_names) for r in records],
        pagination=PaginationMeta(
            page=pagination.page,
            page_size=pagination.page_size,
            total=total,
            total_pages=total_pages,
        ),
    )
