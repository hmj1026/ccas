"""Shared database query helpers."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ccas.storage.models import BankConfig


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
