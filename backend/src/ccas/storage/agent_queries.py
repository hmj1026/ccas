"""Agent read queries SSOT for database operations.

All database reads required by CCAS Agent services live in this module.
Services own validation, DTO mapping, and identity calculations.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import asc, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.storage.models import (
    Bill,
    Budget,
    PipelineRun,
    PipelineRunStatus,
    Transaction,
)


async def get_bill_by_id(session: AsyncSession, bill_id: int) -> Bill | None:
    """Fetch a single Bill by primary key."""
    stmt = select(Bill).where(Bill.id == bill_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def fetch_card_last4s_for_bills(
    session: AsyncSession, bill_ids: Sequence[int]
) -> dict[int, list[str]]:
    """Batch fetch distinct, sorted card_last4s for the specified bill IDs.

    Eliminates N+1 queries when loading cards for multiple bills.
    """
    if not bill_ids:
        return {}

    stmt = (
        select(Transaction.bill_id, Transaction.card_last4)
        .where(
            Transaction.bill_id.in_(bill_ids),
            Transaction.card_last4.isnot(None),
        )
        .order_by(Transaction.card_last4.asc())
    )
    result = await session.execute(stmt)

    mapping: dict[int, set[str]] = {b_id: set() for b_id in bill_ids}
    for b_id, card in result.all():
        if card is not None and card != "":
            mapping[b_id].add(str(card))

    return {b_id: sorted(cards) for b_id, cards in mapping.items()}


async def list_bills_query(
    session: AsyncSession,
    *,
    month: str | None = None,
    year: int | None = None,
    bank_code: str | None = None,
    status: str = "all",
    page: int = 1,
    page_size: int = 20,
) -> tuple[Sequence[Bill], int, int, bool]:
    """Query bills with filtering, sorting (month DESC, bank_code ASC),
    and pagination.
    """
    stmt = select(Bill).order_by(Bill.billing_month.desc(), Bill.bank_code.asc())

    if month is not None:
        stmt = stmt.where(Bill.billing_month == month)
    elif year is not None:
        stmt = stmt.where(Bill.billing_month.startswith(f"{year}-"))

    if bank_code:
        stmt = stmt.where(Bill.bank_code == bank_code)

    if status == "unpaid":
        stmt = stmt.where(Bill.is_paid.is_(False))
    elif status == "paid":
        stmt = stmt.where(Bill.is_paid.is_(True))

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await session.execute(count_stmt)).scalar_one()

    total_pages = max(1, (total + page_size - 1) // page_size)
    has_next = page < total_pages

    paged_stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    bills = (await session.execute(paged_stmt)).scalars().all()

    return bills, total, total_pages, has_next


async def get_payment_due_query(session: AsyncSession) -> Sequence[Bill]:
    """Query all unpaid bills ordered by due_date ascending."""
    stmt = (
        select(Bill)
        .where(Bill.is_paid.is_(False))
        .order_by(Bill.due_date.asc(), Bill.id.asc())
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def query_transactions_query(
    session: AsyncSession,
    *,
    month: str | None = None,
    year: int | None = None,
    bank_code: str | None = None,
    category: str | None = None,
    q: str | None = None,
    sort: str = "trans_date_desc",
    page: int = 1,
    page_size: int = 20,
) -> tuple[Sequence[Any], int, int, bool]:
    """Query transactions with dup_ordinal computed BEFORE user filters.

    Uses a window function (ROW_NUMBER) partitioned by
    (bill_id, trans_date, amount, merchant) ordered by Transaction.id ASC
    across the bill, so duplicates maintain stable ordinals regardless of
    subsequent category/q/bank filters or page slicing.
    """
    dup_ordinal = (
        func.row_number()
        .over(
            partition_by=[
                Transaction.bill_id,
                Transaction.trans_date,
                Transaction.amount,
                Transaction.merchant,
            ],
            order_by=Transaction.id.asc(),
        )
        .label("dup_ordinal")
    )

    base_subq = (
        select(
            Transaction.id,
            Transaction.bill_id,
            Transaction.trans_date,
            Transaction.posting_date,
            Transaction.merchant,
            Transaction.amount,
            Transaction.currency,
            Transaction.original_amount,
            Transaction.card_last4,
            Transaction.category,
            Transaction.installment_current,
            Transaction.installment_total,
            Transaction.created_at,
            Bill.bank_code.label("bill_bank_code"),
            Bill.billing_month.label("bill_billing_month"),
            dup_ordinal,
        )
        .join(Bill, Transaction.bill_id == Bill.id)
        .subquery("txn_ord")
    )

    stmt = select(base_subq)

    # month wins year
    if month is not None:
        stmt = stmt.where(base_subq.c.bill_billing_month == month)
    elif year is not None:
        stmt = stmt.where(base_subq.c.bill_billing_month.startswith(f"{year}-"))

    if bank_code:
        stmt = stmt.where(base_subq.c.bill_bank_code == bank_code)

    if category:
        stmt = stmt.where(base_subq.c.category == category)

    if q:
        stmt = stmt.where(base_subq.c.merchant.contains(q))

    sort_map = {
        "trans_date": base_subq.c.trans_date,
        "amount": base_subq.c.amount,
        "merchant": base_subq.c.merchant,
    }
    col_name, direction = sort.rsplit("_", 1)
    column = sort_map[col_name]
    dir_func = desc if direction == "desc" else asc
    stmt = stmt.order_by(dir_func(column), base_subq.c.id.asc())

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await session.execute(count_stmt)).scalar_one()

    total_pages = max(1, (total + page_size - 1) // page_size)
    has_next = page < total_pages

    paged_stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    rows = (await session.execute(paged_stmt)).all()

    return rows, total, total_pages, has_next


async def list_budgets_query(
    session: AsyncSession,
    *,
    scope: str | None = None,
) -> Sequence[Budget]:
    """Query budgets ordered by ID ascending, optionally filtered by scope."""
    stmt = select(Budget).order_by(Budget.id.asc())
    if scope is not None:
        stmt = stmt.where(Budget.scope == scope)
    result = await session.execute(stmt)
    return result.scalars().all()


async def get_latest_pipeline_run(session: AsyncSession) -> PipelineRun | None:
    """Query the most recent pipeline run ordered by created_at DESC, id DESC."""
    stmt = (
        select(PipelineRun)
        .order_by(PipelineRun.created_at.desc(), PipelineRun.id.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_pipeline_run_by_id(
    session: AsyncSession, run_id: str
) -> PipelineRun | None:
    """Fetch a single PipelineRun by primary key ID."""
    stmt = select(PipelineRun).where(PipelineRun.id == run_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_pipeline_runs_query(
    session: AsyncSession,
    *,
    status: str | PipelineRunStatus | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[Sequence[PipelineRun], int]:
    """Query pipeline runs with optional status filter.

    Sorted by created_at DESC, id DESC.
    """
    count_stmt = select(func.count()).select_from(PipelineRun)
    page_stmt = select(PipelineRun)
    if status is not None:
        count_stmt = count_stmt.where(PipelineRun.status == status)
        page_stmt = page_stmt.where(PipelineRun.status == status)

    page_stmt = (
        page_stmt.order_by(PipelineRun.created_at.desc(), PipelineRun.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    total = (await session.execute(count_stmt)).scalar_one()
    rows = (await session.execute(page_stmt)).scalars().all()
    return rows, total
