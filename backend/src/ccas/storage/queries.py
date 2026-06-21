"""Shared database query helpers."""

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.storage.models import BankConfig, Bill, Budget, BudgetScope, Transaction


async def fetch_bank_names(session: AsyncSession) -> dict[str, str]:
    """Query bank_code -> bank_name mapping for all banks.

    No caching: ``bank_configs`` is a tiny table and a stale per-process
    cache made a Setup UI bank_name change invisible for up to the TTL in
    the other processes (worker / scheduler / bot). A fresh ``SELECT`` per
    call keeps every process consistent at negligible cost.
    """
    stmt = select(BankConfig.bank_code, BankConfig.bank_name)
    result = await session.execute(stmt)
    return {row[0]: row[1] for row in result.all()}


async def aggregate_current_periods(
    session: AsyncSession,
    budgets: Sequence[Budget],
    period_ym: str,
) -> dict[int, int]:
    """Map ``budget_id -> 當月累計花費（NTD 整數元）`` for ``period_ym``.

    以「每個 scope 類型最多一次 grouped query」取代逐筆 budget 聚合（消除 N+1）：
    monthly_total 一次總和、monthly_category 一次 ``GROUP BY category``、
    monthly_bank 一次 ``GROUP BY bank_code``。查詢數恆為 O(1)（≤3），與 budget
    筆數無關。供 budgets router 列表內聯與 budget evaluator 共用，語意與舊的逐筆
    聚合完全一致（同樣以 ``bills.billing_month`` 定義「當月」）。
    """
    scopes = {b.scope for b in budgets}
    total_amount = 0
    by_category: dict[str, int] = {}
    by_bank: dict[str, int] = {}

    if BudgetScope.MONTHLY_TOTAL in scopes:
        stmt = (
            select(func.coalesce(func.sum(Transaction.amount), 0))
            .join(Bill, Transaction.bill_id == Bill.id)
            .where(Bill.billing_month == period_ym)
        )
        # COALESCE 保證非 NULL（空表回 0）；int() 僅為收斂 driver 的聚合回傳型別。
        total_amount = int((await session.execute(stmt)).scalar_one())

    if BudgetScope.MONTHLY_CATEGORY in scopes:
        cat_stmt = (
            select(
                Transaction.category,
                func.coalesce(func.sum(Transaction.amount), 0),
            )
            .join(Bill, Transaction.bill_id == Bill.id)
            .where(Bill.billing_month == period_ym)
            .group_by(Transaction.category)
        )
        for category, amount in (await session.execute(cat_stmt)).all():
            if category is not None:
                by_category[category] = int(amount or 0)

    if BudgetScope.MONTHLY_BANK in scopes:
        bank_stmt = (
            select(
                Bill.bank_code,
                func.coalesce(func.sum(Transaction.amount), 0),
            )
            .join(Transaction, Transaction.bill_id == Bill.id)
            .where(Bill.billing_month == period_ym)
            .group_by(Bill.bank_code)
        )
        for bank_code, amount in (await session.execute(bank_stmt)).all():
            by_bank[bank_code] = int(amount or 0)

    result: dict[int, int] = {}
    for b in budgets:
        if b.scope == BudgetScope.MONTHLY_CATEGORY:
            result[b.id] = by_category.get(b.scope_ref or "", 0)
        elif b.scope == BudgetScope.MONTHLY_BANK:
            result[b.id] = by_bank.get(b.scope_ref or "", 0)
        else:  # MONTHLY_TOTAL（及任何未知 scope 視為 0，與舊邏輯一致）
            result[b.id] = total_amount if b.scope == BudgetScope.MONTHLY_TOTAL else 0
    return result
